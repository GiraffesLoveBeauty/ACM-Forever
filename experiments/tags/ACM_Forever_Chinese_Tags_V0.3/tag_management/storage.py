"""An atomic, independently persisted JSONL event journal with one OS writer lock."""
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from label_pipeline import BASE, TAXONOMY
from .model import VERSION, empty_state, identity, ids, validate_state


def json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON 含重复字段")
        result[key] = value
    return result


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    result = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            row = json.loads(line, object_pairs_hook=json_object)
            if not isinstance(row, dict):
                raise ValueError("JSONL 每行必须是对象")
            result.append(row)
    return result


def safe_journal_path(path):
    path = Path(path).resolve()
    # Also reject nested directories named outputs/cache, including symlink targets.
    if any(part.lower() in {"outputs", "cache"} for part in path.parent.parts):
        raise ValueError("人工修正文件不得位于 outputs 或 cache 目录")
    if path.is_relative_to((BASE / "data").resolve()):
        raise ValueError("人工修正文件不得覆盖题目输入目录")
    if path.suffix.lower() != ".jsonl":
        raise ValueError("人工修正文件必须使用 .jsonl 扩展名")
    return path


class Journal:
    def __init__(self, path):
        self.path = safe_journal_path(path)

    def read(self):
        events = read_jsonl(self.path)
        previous = None
        states, seen = {}, set()
        required = {"schema_version", "event_id", "previous_event_id", "problem_key", "operation",
                    "created_at", "actor", "reason", "taxonomy_version", "before", "after",
                    "automatic_snapshot", "details"}
        for event in events:
            if set(event) != required or event["schema_version"] != VERSION:
                raise ValueError("人工历史版本或字段不兼容")
            key = identity(event["problem_key"])
            eid = event["event_id"]
            if not isinstance(eid, str) or not eid or eid in seen or event["previous_event_id"] != previous:
                raise ValueError("人工历史链损坏或存在重复事件")
            if event["taxonomy_version"] != TAXONOMY["version"]:
                raise ValueError("人工历史标签版本不兼容，请显式迁移")
            if event["operation"] not in {"add", "remove", "replace", "reset", "undo", "verify"}:
                raise ValueError("人工历史包含未知操作")
            if not isinstance(event["actor"], str) or not event["actor"].strip() or not isinstance(event["reason"], str):
                raise ValueError("人工历史操作人或原因字段损坏")
            if not isinstance(event["created_at"], str) or datetime.fromisoformat(event["created_at"]).tzinfo is None:
                raise ValueError("人工历史时间缺少时区")
            before, after = validate_state(event["before"]), validate_state(event["after"])
            if before != states.get(key, empty_state()):
                raise ValueError("人工历史状态不连续")
            snapshot = event["automatic_snapshot"]
            if not isinstance(snapshot, dict) or snapshot.get("problem_key") != key or not isinstance(event["details"], dict):
                raise ValueError("人工历史自动标签快照损坏")
            ids(snapshot.get("tag_ids"))
            states[key] = after
            seen.add(eid)
            previous = eid
        return events, states

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(self.path.suffix + ".lock").open("a+b")
        try:
            if lock.tell() == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise ValueError("人工修正文件正由其他进程写入，请稍后再试") from None
            try:
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            lock.close()

    def write(self, events):
        # Caller holds locked(); replace the whole small journal without deleting history.
        fd, name = tempfile.mkstemp(prefix=".override-", suffix=".tmp", dir=self.path.parent)
        temp = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                for event in events:
                    stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        finally:
            temp.unlink(missing_ok=True)
