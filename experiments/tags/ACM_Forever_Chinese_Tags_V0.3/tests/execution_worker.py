"""Subprocess fixture: synthetic data only; hard exits exercise actual OS lock recovery."""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import os
import socket
import httpx
from problem_processing.executor import execute_batch


def deny(*args, **kwargs):
    raise AssertionError("Worker network forbidden")


if __name__ == "__main__":
    socket.socket.connect = deny
    socket.create_connection = deny
    httpx.HTTPTransport.handle_request = deny
    root, role = Path(sys.argv[1]), sys.argv[2]
    source = {"platform": "atcoder", "problem_key": "atcoder:offline:offline_0", "title": "Mock Addition",
              "statement_markdown": "You are given two integers. Print their sum.", "statement_status": "ok"}
    def checkpoint(stage, row):
        if role.startswith("crash_") and stage == role[6:]:
            os._exit(17)
        if role == "hold" and stage == "claimed":
            (root.parent / "claimed.signal").touch()
            deadline = time.monotonic() + 15
            while not (root.parent / "release.signal").exists():
                if time.monotonic() > deadline:
                    raise RuntimeError("Mock coordination timeout")
                time.sleep(0.02)
    result = execute_batch([source], "annotation", root=root, mock=True, cache_roots=[], manifest_roots=[], checkpoint=checkpoint)
    print(json.dumps({k: v for k, v in result.items() if k != "results"}))
