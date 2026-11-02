"""Read-only diagnostics and verified, portable SQLite + managed image snapshots.

Run: python -m feat.api.acm_api.maintenance --help
Only standard-library modules are used; application startup/migrations are never run.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import sys
import time

STORES = ("forum", "markdown", "avatars")
IMAGE_NAME = re.compile(r"[a-f0-9]{32,48}\.(?:png|jpg|jpeg|webp)")


class MaintenanceError(ValueError):
    pass


def safe_path(value):
    path = Path(os.path.abspath(Path(value).expanduser()))
    for part in (path, *path.parents):
        if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
            raise MaintenanceError("Symbolic links and junctions are not supported")
    return path


def roots(database, markdown_dir=None):
    parent = database.parent / "uploads"
    return {name: safe_path(markdown_dir if name == "markdown" and markdown_dir else parent / name) for name in STORES}


def readonly(database):
    database = safe_path(database)
    if not database.is_file():
        raise MaintenanceError("Database does not exist")
    db = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=5)
    db.execute("PRAGMA query_only=ON")
    return db


def digest(path):
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def image_files(folder):
    if not folder.exists():
        return []
    if not folder.is_dir():
        raise MaintenanceError("Upload root is not a directory")
    result = []
    # Walk without following links, rejecting unexpected files instead of copying secrets.
    for parent, directories, files in os.walk(folder, followlinks=False, onerror=walk_error):
        for name in directories + files:
            path = safe_path(Path(parent) / name)
            if path.is_file():
                if not IMAGE_NAME.fullmatch(path.name):
                    raise MaintenanceError("Unexpected file in managed upload storage")
                result.append(path)
            elif not path.is_dir():
                raise MaintenanceError("Special files are not supported")
    return sorted(result)


def walk_error(error):
    raise error


def database_checks(db):
    integrity = [row[0] for row in db.execute("PRAGMA integrity_check")]
    violations = sum(1 for _ in db.execute("PRAGMA foreign_key_check"))
    return {"integrity_ok": integrity == ["ok"], "foreign_key_violations": violations}


def diagnose(database, markdown_dir=None):
    database = safe_path(database)
    stores = roots(database, markdown_dir)
    with closing(readonly(database)) as db:
        checks = database_checks(db)
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        references = {name: set() for name in STORES}
        invalid = 0
        for table, query, store in [
            ("forum_images", "SELECT id || '.webp' FROM forum_images", "forum"),
            ("markdown_assets", "SELECT storage_name FROM markdown_assets", "markdown"),
            ("users", "SELECT substr(avatar_url,18) FROM users WHERE avatar_url LIKE '/uploads/avatars/%'", "avatars"),
        ]:
            if table not in tables:
                continue
            if table == "users" and "avatar_url" not in {row[1] for row in db.execute("PRAGMA table_info(users)")}:
                continue
            for (name,) in db.execute(query):
                if isinstance(name, str) and IMAGE_NAME.fullmatch(name):
                    references[store].add(name)
                else:
                    invalid += 1
    storage = {}
    for name, folder in stores.items():
        files = image_files(folder)
        missing = sum(not (folder / reference).is_file() for reference in references[name])
        storage[name] = {"exists": folder.is_dir(), "files": len(files), "referenced": len(references[name]), "missing": missing}
    return {
        "ok": checks["integrity_ok"] and not checks["foreign_key_violations"] and not invalid and not any(s["missing"] for s in storage.values()),
        "database": checks,
        "storage": storage,
        "invalid_asset_references": invalid,
        "free_bytes": shutil.disk_usage(database.parent).free,
    }


def separate(destination, sources):
    for source in sources:
        if destination == source or destination in source.parents or source in destination.parents:
            raise MaintenanceError("Source and destination must not overlap")


def copy_new(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as incoming, destination.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, 1024 * 1024)


def backup(database, destination, *, markdown_dir=None, writers_stopped=False):
    if not writers_stopped:
        raise MaintenanceError("Stop all writers first, then pass --writers-stopped")
    database, destination = safe_path(database), safe_path(destination)
    stores = roots(database, markdown_dir)
    separate(destination, [database.parent, *stores.values()])
    report = diagnose(database, markdown_dir)
    if not report["ok"]:
        raise MaintenanceError("Source diagnostics failed; inspect diagnose before backup")
    # Never overwrite: an interrupted backup has no manifest and cannot be verified/restored.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = time.monotonic()
    def progress(status, remaining, total):
        if time.monotonic() - started > 120:
            raise MaintenanceError("SQLite backup timed out")
    with closing(readonly(database)) as source, closing(sqlite3.connect(destination / "database.sqlite3")) as target:
        source.backup(target, pages=256, progress=progress, sleep=0.05)
        # A portable snapshot is a single DB file; read-only verification must not create WAL sidecars.
        target.execute("PRAGMA journal_mode=DELETE")
    for name, folder in stores.items():
        for path in image_files(folder):
            copy_new(path, destination / "uploads" / name / path.relative_to(folder))
    files = {}
    for path in sorted(destination.rglob("*")):
        if path.is_file():
            files[path.relative_to(destination).as_posix()] = {"size": path.stat().st_size, "sha256": digest(path)}
    manifest = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(), "files": files}
    with (destination / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    return verify(destination)


def manifest_name(value):
    if not isinstance(value, str) or "\\" in value or ":" in value:
        raise MaintenanceError("Unsafe manifest path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(p in {".", ".."} for p in path.parts):
        raise MaintenanceError("Unsafe manifest path")
    if value == "database.sqlite3":
        return path
    if len(path.parts) < 3 or path.parts[0] != "uploads" or path.parts[1] not in STORES or not IMAGE_NAME.fullmatch(path.name):
        raise MaintenanceError("Unexpected manifest entry")
    return path


def verify(snapshot):
    snapshot = safe_path(snapshot)
    manifest_path = safe_path(snapshot / "manifest.json")
    if not manifest_path.is_file() or manifest_path.stat().st_size > 64 * 1024 * 1024:
        raise MaintenanceError("Missing or oversized manifest")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise MaintenanceError("Invalid manifest JSON") from error
    if not isinstance(manifest, dict) or manifest.get("version") != 1 or not isinstance(manifest.get("files"), dict):
        raise MaintenanceError("Unsupported manifest")
    files = manifest["files"]
    if "database.sqlite3" not in files:
        raise MaintenanceError("Snapshot has no database")
    for name, metadata in files.items():
        relative = manifest_name(name)
        path = safe_path(snapshot / relative)
        if not isinstance(metadata, dict) or type(metadata.get("size")) is not int or metadata["size"] < 0 or not re.fullmatch(r"[a-f0-9]{64}", str(metadata.get("sha256", ""))):
            raise MaintenanceError("Invalid checksum entry")
        if not path.is_file() or path.stat().st_size != metadata["size"] or digest(path) != metadata["sha256"]:
            raise MaintenanceError("Missing or altered snapshot file: " + name)
    actual = set()
    for parent, directories, names in os.walk(snapshot, followlinks=False, onerror=walk_error):
        for name in directories + names:
            path = safe_path(Path(parent) / name)
            if path.is_file():
                actual.add(path.relative_to(snapshot).as_posix())
            elif not path.is_dir():
                raise MaintenanceError("Unexpected special file")
    if actual != set(files) | {"manifest.json"}:
        raise MaintenanceError("Snapshot contains unlisted files")
    report = diagnose(snapshot / "database.sqlite3")
    if not report["ok"]:
        raise MaintenanceError("Snapshot database or asset references failed validation")
    return {"ok": True, "files": len(files), "bytes": sum(item["size"] for item in files.values()), "diagnostics": report}


def restore(snapshot, destination):
    snapshot, destination = safe_path(snapshot), safe_path(destination)
    separate(destination, [snapshot])
    verify(snapshot)
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Copy into a new directory only; verify the copy again before reporting success.
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    for name in [*manifest["files"], "manifest.json"]:
        relative = PurePosixPath(name) if name == "manifest.json" else manifest_name(name)
        copy_new(safe_path(snapshot / relative), safe_path(destination / relative))
    return verify(destination)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("diagnose", "backup"):
        command = commands.add_parser(name)
        command.add_argument("--database", required=True, type=Path)
        command.add_argument("--markdown-dir", type=Path, help="Match ACM_MARKDOWN_UPLOAD_DIR when overridden")
        if name == "backup":
            command.add_argument("--destination", required=True, type=Path)
            command.add_argument("--writers-stopped", action="store_true")
    command = commands.add_parser("verify")
    command.add_argument("snapshot", type=Path)
    command = commands.add_parser("restore")
    command.add_argument("snapshot", type=Path)
    command.add_argument("--destination", required=True, type=Path)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    try:
        result = {"diagnose": diagnose, "backup": backup, "verify": verify, "restore": restore}[command](**args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1
    except (MaintenanceError, OSError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
