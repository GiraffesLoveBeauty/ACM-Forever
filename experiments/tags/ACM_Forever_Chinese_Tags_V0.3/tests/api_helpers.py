"""Synthetic fixtures only; never send traffic or use a real credential."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from annotation_api.config import Config
from annotation_api.client import Response


def sample(platform="atcoder", number=1, tags=None):
    contest = "demo001" if platform == "atcoder" else "999999"
    pid = f"demo001_{number}" if platform == "atcoder" else chr(64 + number)
    return {"problem_key": f"{platform}:{contest}:{pid}", "platform": platform,
            "title": "模拟静态区间求和", "raw_tags": tags or [],
            "statement_markdown": "静态数组，回答多次区间和查询，N,Q<=200000。",
            "statement_status": "ok", "editorial_status": "missing"}


def config(**kwargs):
    return Config(**{"provider": "openai", "model": "offline-model", "api_key": "offline-test-key",
                     "request_interval": 0, **kwargs})


def wire(data, **kwargs):
    return {"problem_key": data["problem_key"], "content_hash": data["content_hash"],
            "specific_tag_ids": ["prefix_sum"], "provisional_tag_ids": [], "resolved_cf_hints": [],
            "evidence_kind": "statement_only", "reason": "静态数组使用前缀和回答查询。", **kwargs}


def save_rows(path, rows):
    Path(path).write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rows), encoding="utf-8")


class FakeClient:
    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = 0

    def call(self, messages):
        self.calls += 1
        data = json.loads(messages[1]["content"])
        result = self.outcomes.pop(0) if self.outcomes else None
        if isinstance(result, BaseException):
            raise result
        if callable(result):
            result = result(data)
        if isinstance(result, Response):
            return result
        return Response(content=json.dumps(wire(data, **(result or {})), ensure_ascii=False),
                        model="offline-model-response", usage={"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                        finish_reason="stop")
