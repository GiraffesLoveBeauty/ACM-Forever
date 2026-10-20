"""Atomic cache and recoverable UTF-8 JSONL output. One writer per run."""
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone
from .adapter import human_confirmed


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(".tmp-" + uuid.uuid4().hex)
    try:
        with temp.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def read_jsonl(path, *, repair_tail=False):
    path = Path(path)
    if not path.exists():
        return []
    data = path.read_bytes()
    lines = data.splitlines(keepends=True)
    out, offset = [], 0
    for index, line in enumerate(lines):
        if not line.strip():
            offset += len(line)
            continue
        try:
            value = json.loads(line.decode("utf-8-sig"))
            if not isinstance(value, dict):
                raise ValueError("JSONL record must be object")
            out.append(value)
        except (ValueError, UnicodeError):
            if not repair_tail or index != len(lines) - 1 or line.endswith(b"\n"):
                raise ValueError("Corrupt JSONL record; only an incomplete tail can be repaired") from None
            with path.open("r+b") as f:
                f.truncate(offset)
                f.flush()
                os.fsync(f.fileno())
            break
        offset += len(line)
    if repair_tail and path.exists() and path.stat().st_size and not path.read_bytes().endswith(b"\n"):
        with path.open("ab") as f:
            f.write(b"\n")
            f.flush()
            os.fsync(f.fileno())
    return out


class Store:
    def __init__(self, output, cache_root, profile, profile_id, resume=False):
        self.output, self.cache_root = Path(output), Path(cache_root)
        self.profile, self.profile_id, self.resume = profile, profile_id, resume
        self.lock = None

    def __enter__(self):
        self.output.mkdir(parents=True, exist_ok=True)
        self.lock = (self.output / ".writer.lock").open("a+b")
        if self.lock.tell() == 0:
            self.lock.write(b"0")
            self.lock.flush()
        self.lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            self.lock = None
            raise ValueError("Output is locked by another annotation process") from None
        try:
            manifest = self.output / "manifest.json"
            if manifest.exists():
                old = json.loads(manifest.read_text(encoding="utf-8"))
                if old["profile"] != self.profile:
                    raise ValueError("Output belongs to another model/dataset/version configuration")
                if not self.resume:
                    raise ValueError("Existing output requires --resume; overwriting is forbidden")
            else:
                if any((self.output / name).exists() for name in ("predictions.jsonl", "merged_results.jsonl", "errors.jsonl")):
                    raise ValueError("Unmanaged output files exist; use a fresh directory")
                atomic_json(manifest, {"profile_id": self.profile_id, "profile": self.profile, "selected": []})
            for name in ("predictions.jsonl", "merged_results.jsonl", "errors.jsonl"):
                path = self.output / name
                if path.exists():
                    read_jsonl(path, repair_tail=True)
                else:
                    path.touch()
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *_):
        if self.lock:
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock.fileno(), fcntl.LOCK_UN)
            self.lock.close()
            self.lock = None

    def set_selection(self, items):
        old = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        selected = {x["problem_key"]: x for x in old["selected"]}
        for item in items:
            row = {"problem_key": item["rule_base"]["problem_key"],
                   "content_hash": item["rule_base"]["content_hash"],
                   "annotation_input_hash": item["annotation_input_hash"]}
            if row["problem_key"] in selected and selected[row["problem_key"]] != row:
                raise ValueError("Dataset identity/content changed within an output directory")
            selected[row["problem_key"]] = row
        atomic_json(self.output / "manifest.json", {"profile_id": self.profile_id, "profile": self.profile,
                    "selected": list(selected.values())})

    def cache_path(self, fingerprint):
        # Cache is scoped to output as well as request profile: its writer lock protects it.
        from .adapter import digest
        namespace = digest({"output": str(self.output.resolve()), "profile": self.profile_id})
        return self.cache_root / namespace / (fingerprint + ".json")

    def load(self, fingerprint):
        path = self.cache_path(fingerprint)
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

    def save(self, fingerprint, value):
        atomic_json(self.cache_path(fingerprint), value)

    def rows(self, name):
        return read_jsonl(self.output / name)

    def append_once(self, name, value):
        token = value.get("error_id") or value.get("request_fingerprint")
        rows = self.rows(name)
        if any((x.get("error_id") or x.get("request_fingerprint")) == token for x in rows):
            return
        with (self.output / name).open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def protected(self, key):
        return next((x for x in self.rows("merged_results.jsonl") if x.get("problem_key") == key and human_confirmed(x)), None)

    def save_merged(self, value):
        old = self.protected(value["problem_key"])
        if old:
            return  # Persisted human results are never replaced, including by changed review input.
        rows = self.rows("merged_results.jsonl")
        previous = next((x for x in rows if x.get("request_fingerprint") == value["request_fingerprint"]), None)
        if human_confirmed(value) or (previous and previous.get("api_call_status") != value.get("api_call_status")):
            rows = [x for x in rows if x.get("problem_key") != value["problem_key"]] + [value]
            path = self.output / "merged_results.jsonl"
            temp = path.with_name(".tmp-" + uuid.uuid4().hex)
            try:
                with temp.open("w", encoding="utf-8", newline="\n") as f:
                    for row in rows:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)
        else:
            self.append_once("merged_results.jsonl", value)
