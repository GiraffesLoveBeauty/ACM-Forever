"""Durable task records and OS locks. No lease expiry can authorize another request."""
import json
import re
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from datetime import datetime

from annotation_api.adapter import digest
from annotation_api.storage import atomic_json, now
from tag_management.storage import Journal
from .backup import checked_path, check_sensitive

STATES = {"pending", "claimed", "dispatched", "completed", "failed_before_dispatch", "uncertain", "blocked"}
HEX = re.compile(r"[0-9a-f]{64}")


class Busy(ValueError):
    pass


def read_record(path):
    value = json.loads(checked_path(path).read_text(encoding="utf-8"))
    check_sensitive(value)
    return value


class Ledger:
    def __init__(self, root):
        self.root = checked_path(root) / "execution"

    def path(self, kind, identity):
        if kind not in {"tasks", "responses", "results"} or not HEX.fullmatch(identity):
            raise ValueError("非法执行状态路径")
        return checked_path(self.root / kind / (identity + ".json"))

    def load(self, task_id):
        path = self.path("tasks", task_id)
        if not path.exists():
            return None
        row = read_record(path)
        fields = {"version", "task_id", "identity", "problem_key", "task_type", "created_at", "updated_at", "attempts",
                  "input_problem", "state", "attempt_id", "response_sha256", "result_sha256", "error", "request_sha256",
                  "http_status", "elapsed_seconds"}
        if not set(row) <= fields:
            raise ValueError("执行记录包含未经审查的字段")
        if row.get("task_id") != task_id or row.get("state") not in STATES or row.get("version") != 1:
            raise ValueError("任务记录损坏")
        if digest(row["identity"]) != task_id:
            raise ValueError("任务身份摘要损坏")
        meta = row["identity"]
        if (set(meta) != {"version", "problem_key", "task_type", "input_semantic_hash", "policy", "request_settings", "mode"}
                or meta["version"] != 1 or meta["problem_key"] != row["problem_key"] or meta["task_type"] != row["task_type"]
                or meta["mode"] not in {"mock", "live"} or row["task_type"] not in {"annotation", "translation"}
                or not HEX.fullmatch(meta["input_semantic_hash"])
                or set(meta["request_settings"]) != {"provider", "base_url", "model", "response_format", "token_parameter", "max_output_tokens"}):
            raise ValueError("任务身份字段不兼容")
        policies = {"revision", "prompt_hash", "schema_hash"}
        policies |= {"taxonomy_hash", "mapping_hash", "rule_version"} if row["task_type"] == "annotation" else {"target_language"}
        if set(meta["policy"]) != policies:
            raise ValueError("任务策略字段不兼容")
        if not row["attempts"] or row["attempts"][-1]["attempt_id"] != row["attempt_id"]:
            raise ValueError("任务尝试链损坏")
        for attempt in row["attempts"]:
            if set(attempt) != {"attempt_id", "created_at", "events"} or not HEX.fullmatch(attempt["attempt_id"]):
                raise ValueError("任务尝试字段损坏")
            for event in attempt["events"]:
                if set(event) != {"state", "at"} or event["state"] not in STATES or datetime.fromisoformat(event["at"]).tzinfo is None:
                    raise ValueError("执行事件损坏")
        if row["attempts"][-1]["events"][-1]["state"] != row["state"]:
            raise ValueError("执行状态与事件不一致")
        from .adapter import normalize
        from .planning import semantic_inputs
        p = normalize(row["input_problem"])
        if p["problem_key"] != row["problem_key"] or digest(semantic_inputs(p)[0 if row["task_type"] == "annotation" else 1]) != meta["input_semantic_hash"]:
            raise ValueError("执行输入绑定损坏")
        return row

    def records(self):
        folder = checked_path(self.root / "tasks")
        return [self.load(p.stem) for p in sorted(folder.glob("*.json"))] if folder.exists() else []

    @contextmanager
    def locked(self, key, task_type):
        scope = digest({"problem_key": key, "task_type": task_type})
        guard = Journal(checked_path(self.root / "locks" / (scope + ".jsonl"))).locked()
        try:
            guard.__enter__()
        except ValueError:
            raise Busy("同一题目的同类任务已被另一进程占用") from None
        try:
            yield
        finally:
            guard.__exit__(None, None, None)

    def claim(self, identity, problem):
        task_id = digest(identity)
        old = self.load(task_id)
        if old and old["state"] not in {"failed_before_dispatch", "pending"}:
            raise ValueError("当前任务状态不允许领取")
        timestamp = now()
        row = old or {"version": 1, "task_id": task_id, "identity": identity,
                      "problem_key": problem["problem_key"], "task_type": identity["task_type"],
                      "created_at": timestamp, "attempts": [], "input_problem": problem}
        row.update(state="claimed", updated_at=timestamp, attempt_id=digest(uuid4().hex),
                   response_sha256=None, result_sha256=None, error=None, input_problem=problem)
        row["attempts"].append({"attempt_id": row["attempt_id"], "created_at": timestamp,
                                "events": [{"state": "claimed", "at": timestamp}]})
        self.save(row)
        return row

    def save(self, row):
        check_sensitive(row)
        atomic_json(self.path("tasks", row["task_id"]), row)

    def transition(self, row, state, **fields):
        if state not in STATES:
            raise ValueError("非法任务状态")
        transitions = {"claimed": {"failed_before_dispatch", "dispatched", "blocked"},
                       "dispatched": {"completed", "uncertain", "blocked"},
                       "uncertain": {"completed", "blocked"},
                       "completed": set(), "blocked": set(), "failed_before_dispatch": set()}
        if state not in transitions.get(row["state"], set()):
            raise ValueError("禁止的执行状态转换")
        row.update(fields, state=state, updated_at=now())
        row["attempts"][-1]["events"].append({"state": state, "at": row["updated_at"]})
        self.save(row)

    def save_artifact(self, kind, identity, value):
        path = self.path(kind, identity)
        check_sensitive(value)
        if path.exists():
            if read_record(path) != value:
                raise ValueError("不可覆盖原始响应或结果")
        else:
            atomic_json(path, value)
        return digest(value)

    def artifact(self, kind, identity, expected=None):
        value = read_record(self.path(kind, identity))
        if expected and digest(value) != expected:
            raise ValueError("执行产物摘要损坏")
        return value
