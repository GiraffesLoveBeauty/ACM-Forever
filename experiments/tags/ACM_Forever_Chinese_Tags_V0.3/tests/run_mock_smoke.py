"""Generate explicitly synthetic demo artifacts through SDK MockTransport.

No .env is read and no real HTTP transport is created.
"""
import json
from unittest.mock import patch
import httpx
from api_helpers import sample, config, wire, save_rows
from annotation_api.client import APIClient
from annotation_api.runner import run, profile_for
from annotation_api.adapter import digest
from annotation_api.storage import atomic_json
from label_pipeline import BASE


def main():
    root = BASE / "outputs" / "mock_smoke"
    root.mkdir(parents=True, exist_ok=True)
    inputs = root / "synthetic_inputs.jsonl"
    save_rows(inputs, [sample(), sample("codeforces", tags=["dsu", "data structures"])])
    output = root / "runs" / digest(profile_for(config(), inputs))[:16]

    def handler(request):
        data = json.loads(json.loads(request.content)["messages"][1]["content"])
        return httpx.Response(200, json={"id": "mock-only", "object": "chat.completion", "created": 0,
                "model": "offline-mock-model", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": json.dumps(wire(data), ensure_ascii=False)}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}})

    with patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Real network forbidden")):
        client = APIClient(config(), http_client=httpx.Client(transport=httpx.MockTransport(handler)))
        try:
            summary = run(inputs, config(), output=output, client=client, resume=True, sleep=lambda _: None)
        finally:
            client.close()
    summary.update(mode="mock", real_api_calls=0)
    atomic_json(output / "summary.json", summary)
    atomic_json(root / "MOCK_ONLY.json", {"mode": "mock", "real_api_calls": 0, "output": str(output.resolve()),
                "warning": "仅虚构题目的 Mock 输出；Token 数为模拟值，不是实际题目标注或费用记录。"})
    print(json.dumps({"mode": "mock", "real_api_calls": 0, "summary": summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
