"""Offline snapshots: immutable source, verified payload, isolated restoration only."""
import hashlib
import json
import math
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4

from annotation_api.adapter import digest
from label_pipeline import BASE, TAXONOMY
from tag_management.model import identity
from tag_management.service import auto_record
from tag_management.storage import Journal, json_object
from .repository import PROJECT_ROOT, Repository

BACKUP_VERSION = 1
HEX = r"[0-9a-f]{64}"
VERSION_FILES = ("tag_taxonomy_v0.3.json", "cf_mapping_v0.3.json", "ai_annotation_prompt_v0.3.md")
ERROR_CODES = {"unknown_delivery", "quota_exhausted", "rate_limit", "api_configuration_error",
               "invalid_annotation", "invalid_translation", "refusal", "incomplete_output",
               "empty_output", "missing_statement"}
STATES = {"prepared", "sent", "retry_wait", "received", "success", "failed", "unknown_delivery"}
SENSITIVE_KEYS = {"apikey", "openaiapikey", "authorization", "proxyauthorization",
                  "headers", "requestheaders", "authentication", "credentials", "password",
                  "secret", "accesstoken", "refreshtoken", "cookie", "setcookie"}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def parse(data):
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=json_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("非有限 JSON 数字")))


def rows(data):
    result = [parse(line) for line in data.splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in result):
        raise ValueError("JSONL 必须为对象记录")
    return result


def safe_relative(value):
    # One portable spelling prevents Windows drive/ADS/device/case aliases.
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("非法备份路径")
    parts = value.split("/")
    for part in parts:
        if (not part or part in {".", ".."} or part.endswith((".", " ")) or
                re.search(r'[\x00-\x1f<>:"|?*]', part) or
                re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?", part)):
            raise ValueError("非法备份路径")
    if PurePosixPath(value).is_absolute():
        raise ValueError("非法备份路径")
    return value


def checked_path(value):
    path = Path(os.path.abspath(os.fspath(value)))
    for ancestor in [*reversed(path.parents), path]:
        try:
            info = ancestor.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 1024):
            raise ValueError("拒绝符号链接或 Windows 重解析点")
    return path


def inventory(root):
    root = checked_path(root)
    if not root.is_dir():
        raise ValueError("数据目录不存在")
    files, directories = {}, []
    for folder, names, filenames in os.walk(root, followlinks=False):
        for name in sorted(names + filenames):
            path = checked_path(Path(folder) / name)
            rel = safe_relative(path.relative_to(root).as_posix())
            if path.is_dir():
                directories.append(rel)
            elif stat.S_ISREG(path.lstat().st_mode):
                files[rel] = path.read_bytes()
            else:
                raise ValueError("拒绝非普通数据文件")
    return files, sorted(directories)


def allowed_data_path(path):
    return bool(re.fullmatch(
        rf"(?:annotations/{HEX}\.jsonl|catalog/current\.json|"
        rf"catalog/generations/{HEX}/(?:manifest\.json|problems\.jsonl|auto_tags\.jsonl)|"
        rf"manual/overrides\.jsonl|translations/current\.json|"
        rf"translations/(?:history|requests)/{HEX}\.json|exports/[A-Za-z0-9_.-]+\.jsonl?|"
        rf"exports/[A-Za-z0-9_.-]+\.json)", path))


def allowed_data_directory(path):
    return bool(re.fullmatch(rf"(?:annotations|catalog|catalog/generations|catalog/generations/{HEX}|"
                             r"manual|translations|translations/history|translations/requests|exports)", path))


def check_sensitive(value):
    # Source records are retained byte-for-byte; suspected secrets cause rejection, never redaction.
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in SENSITIVE_KEYS or normalized.endswith("apikey"):
                raise ValueError("数据包含敏感配置字段，拒绝备份（内容未输出）")
            check_sensitive(item)
    elif isinstance(value, list):
        for item in value:
            check_sensitive(item)
    elif isinstance(value, str) and re.search(r"(?i)\bsk-[A-Za-z0-9_-]{12,}|\bBearer\s+\S+|https?://[^/\s]+:[^/\s]+@", value):
        raise ValueError("数据疑似包含认证信息，拒绝备份（内容未输出）")


def safe_usage(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("请求用量格式损坏")
    out = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in value:
            if type(value[key]) is not int or value[key] < 0:
                raise ValueError("请求用量数字损坏")
            out[key] = value[key]
    return out


def request_state(value):
    """Explicit allowlist; raw responses, exception text, headers, config are never copied."""
    if not isinstance(value, dict) or value.get("state") not in STATES:
        raise ValueError("请求状态损坏")
    out = {"state": value["state"]}
    for key in ("error", "error_code"):
        if key in value:
            out[key] = value[key] if isinstance(value[key], str) and value[key] in ERROR_CODES else "redacted_error"
    for key in ("fingerprint", "profile_id"):
        if key in value:
            if not isinstance(value[key], str) or not re.fullmatch(HEX, value[key]):
                raise ValueError("请求指纹损坏")
            out[key] = value[key]
    if "problem_key" in value:
        out["problem_key"] = identity(value["problem_key"])
    for key in ("http_status", "elapsed_seconds"):
        number = value.get(key)
        if number is None:
            if key in value:
                out[key] = None
        elif type(number) in (int, float) and math.isfinite(number) and number >= 0:
            out[key] = number
        else:
            raise ValueError("请求统计字段损坏")
    if type(value.get("fatal")) is bool:
        out["fatal"] = value["fatal"]
    if "usage" in value:
        out["usage"] = safe_usage(value["usage"])
    if "attempts" in value:
        if not isinstance(value["attempts"], list):
            raise ValueError("请求尝试记录损坏")
        out["attempts"] = []
        for attempt in value["attempts"]:
            if not isinstance(attempt, dict):
                raise ValueError("请求尝试记录损坏")
            out["attempts"].append(request_state({**attempt, "state": "received"}) | {
                "status": attempt.get("status") if attempt.get("status") in ERROR_CODES | {"received"} else "redacted_status"})
    response = value.get("response")
    if response is not None:
        if not isinstance(response, dict):
            raise ValueError("请求响应记录损坏")
        out["response_statistics"] = {"usage": safe_usage(response.get("usage"))}
    elif "response_statistics" in value:
        if not isinstance(value["response_statistics"], dict):
            raise ValueError("请求响应统计损坏")
        out["response_statistics"] = {"usage": safe_usage(value["response_statistics"].get("usage"))}
    return out


def validate_dataset(root, files):
    """Reuse repository/journal/tag validation; additionally check every historical generation."""
    if "catalog/current.json" not in files:
        raise ValueError("缺少当前目录版本指针")
    for directory in ("annotations", "catalog", "manual", "translations", "exports"):
        if not (Path(root) / directory).is_dir():
            raise ValueError("持久数据目录不完整")
    versions, known_keys, annotations = set(), set(), 0
    for path, data in files.items():
        if not allowed_data_path(path):
            raise ValueError("不支持的持久文件路径")
        value = rows(data) if path.endswith(".jsonl") else parse(data)
        check_sensitive(value)
        if path.startswith("annotations/"):
            if digest(value) != Path(path).stem:
                raise ValueError("自动标注历史摘要损坏")
            for row in value:
                auto_record(row)
            annotations += len(value)
        if re.fullmatch(rf"catalog/generations/{HEX}/manifest\.json", path):
            gid = path.split("/")[2]; versions.add(gid)
            if value.get("generation_id") != gid or value.get("taxonomy_version") != TAXONOMY["version"]:
                raise ValueError("历史版本信息不兼容")
            prefix = f"catalog/generations/{gid}/"
            if prefix + "problems.jsonl" not in files or prefix + "auto_tags.jsonl" not in files:
                raise ValueError("历史版本文件缺失")
            ps, ls = rows(files[prefix + "problems.jsonl"]), rows(files[prefix + "auto_tags.jsonl"])
            if digest({"problems": ps, "auto_tags": ls}) != gid or value.get("problem_count") != len(ps):
                raise ValueError("历史版本哈希或数量不一致")
            keys = [identity(p["problem_key"]) for p in ps]
            autos = [auto_record(a) for a in ls]
            if len(set(keys)) != len(keys) or len({a["problem_key"] for a in autos}) != len(autos):
                raise ValueError("历史目录存在重复题目")
            if set(keys) != {a["problem_key"] for a in autos}:
                raise ValueError("题目与标签身份不对应")
            problems = {p["problem_key"]: p for p in ps}
            from .adapter import source_identity
            for p in ps:
                if source_identity({"problem_key": p["problem_key"], "platform": p["platform"],
                                    "problem_id": p["source_problem_id"], "contest_id": p["contest_id"]})[3] != p["problem_key"]:
                    raise ValueError("题目身份损坏")
                if digest({"title": p["original_title"], "text": p["original_statement"], "html": p["original_statement_html"]}) != p["verified_content_hash"]:
                    raise ValueError("题面校验哈希损坏")
            if any(a["content_hash"] != problems[a["problem_key"]]["content_hash"] for a in autos):
                raise ValueError("题面与自动标签哈希不对应")
            known_keys.update(keys)
    actual_generations = {p.split("/")[2] for p in files if p.startswith("catalog/generations/")}
    if versions != actual_generations:
        raise ValueError("存在不完整目录版本")
    pointer = parse(files["catalog/current.json"])
    if set(pointer) != {"generation_id"} or pointer["generation_id"] not in versions:
        raise ValueError("当前版本指针无效")
    repo = Repository(root)
    ps, _ = repo.snapshot()
    events, _ = Journal(Path(root) / "manual" / "overrides.jsonl").read()
    if any(e["problem_key"] not in known_keys for e in events):
        raise ValueError("人工历史无法对应题目目录")
    views = repo.manager().get_effective_tags_many(list(ps))
    translations = {}
    for path, data in files.items():
        if path.startswith("translations/history/"):
            row = parse(data); fp = Path(path).stem
            if row.get("request_fingerprint") != fp or row.get("problem_key") not in known_keys:
                raise ValueError("翻译身份或请求指纹不对应")
            if not row.get("translation_version") or not row.get("source_content_hash") or not row.get("source_verified_hash"):
                raise ValueError("翻译版本或源哈希缺失")
            if row.get("translation_status") not in {"auto", "mock", "needs_review"}:
                raise ValueError("翻译状态不兼容")
            translations[fp] = row
        if path.startswith("translations/requests/"):
            row = parse(data)
            request_state(row)
            if row.get("fingerprint", Path(path).stem) != Path(path).stem or row.get("problem_key") is not None and row["problem_key"] not in known_keys:
                raise ValueError("翻译请求身份或指纹损坏")
            if row["state"] == "success" and f"translations/history/{Path(path).stem}.json" not in files:
                raise ValueError("成功翻译缺少已付费结果")
    index = parse(files["translations/current.json"]) if "translations/current.json" in files else {}
    if not isinstance(index, dict):
        raise ValueError("翻译索引格式错误")
    for key, fp in index.items():
        if key not in known_keys or not isinstance(fp, str) or fp not in translations or translations[fp]["problem_key"] != key or translations[fp]["translation_status"] != "auto":
            raise ValueError("翻译索引指向错误题目或缺失版本")
    return {"generation_id": pointer["generation_id"], "generations": len(versions), "problems": len(ps),
            "annotation_records": annotations, "manual_events": len(events), "translations": len(translations),
            "translation_requests": sum(p.startswith("translations/requests/") for p in files),
            "effective_view_sha256": digest(views), "taxonomy_version": TAXONOMY["version"]}


def backup_root(value=None):
    root = checked_path(value or os.environ.get("TAG_BACKUP_ROOT") or
                        (PROJECT_ROOT.parent / (PROJECT_ROOT.name + "-Backups") / "labels"))
    if root.is_relative_to(PROJECT_ROOT):
        raise ValueError("备份必须位于 Git 仓库之外")
    return root


def write_new(path, data):
    path = checked_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    checked_path(path.parent)
    with path.open("xb") as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())


def create_backup(root=None, destination=None, *, request_root=None):
    # Validate the raw configured path before Repository.data_root() resolves links away.
    source_input = Path(root or os.environ.get("TAG_DATA_ROOT") or PROJECT_ROOT / "data" / "labels")
    source = checked_path(source_input if source_input.is_absolute() else PROJECT_ROOT / source_input)
    dest = backup_root(destination)
    if dest.is_relative_to(source) or source.is_relative_to(dest):
        raise ValueError("备份与源数据目录不能嵌套")
    before, directories = inventory(source)
    selected, excluded, transformed = {}, [], []
    for path, data in before.items():
        if path.endswith(".lock") or Path(path).name.startswith((".tmp-", ".override-")):
            excluded.append(path); continue
        if not allowed_data_path(path):
            # Sensitive and unexpected files are never silently included.
            raise ValueError("源目录含未审查文件，请先检查（文件内容未输出）")
        selected[path] = data
    if any(not allowed_data_directory(p) for p in directories):
        raise ValueError("源目录含未审查子目录")
    counts = validate_dataset(source, selected)
    payload = {"payload/" + p: data for p, data in selected.items()}
    for path, data in selected.items():
        if path.startswith("translations/requests/"):
            cleaned = json_bytes(request_state(parse(data)))
            payload["payload/" + path] = cleaned
            if cleaned != data:
                transformed.append("payload/" + path)
    for name in VERSION_FILES:
        payload["versions/" + name] = (BASE / name).read_bytes()
    req = checked_path(request_root) if request_root is not None else None
    requests_before, requests_dirs = inventory(req) if req is not None else ({}, [])
    if any(not re.fullmatch(HEX, d) for d in requests_dirs):
        raise ValueError("标注请求目录结构不兼容")
    for path, data in requests_before.items():
        if not re.fullmatch(rf"{HEX}/{HEX}\.json", path):
            raise ValueError("标注请求文件路径不兼容")
        payload["request_states/" + path] = json_bytes(request_state(parse(data)))
        transformed.append("request_states/" + path)
    after, after_dirs = inventory(source)
    if (before, directories) != (after, after_dirs) or (req is not None and inventory(req) != (requests_before, requests_dirs)):
        raise ValueError("备份期间数据变化，未发布备份；请暂停写入后重试")
    created = datetime.now(timezone.utc)
    target = dest / (created.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8])
    target.mkdir(parents=True, exist_ok=False)
    all_dirs = {"payload", "versions"} | {"payload/" + d for d in directories}
    for path in payload:
        all_dirs.update(str(p) for p in PurePosixPath(path).parents if str(p) != ".")
    for directory in sorted(all_dirs):
        checked_path(target / directory).mkdir(parents=True, exist_ok=True)
    for path, data in sorted(payload.items()):
        write_new(target / path, data)
    manifest = {"backup_version": BACKUP_VERSION, "created_at": created.isoformat(), "counts": counts,
                "annotation_request_states": len(requests_before), "directories": sorted(all_dirs),
                "files": [{"path": p, "sha256": sha256(data), "bytes": len(data)} for p, data in sorted(payload.items())],
                "file_count": len(payload), "total_bytes": sum(map(len, payload.values())),
                "excluded_runtime_files": sorted(excluded), "allowlist_transformed_files": sorted(transformed),
                "request_policy": "status-only-v1; no headers/config/raw response; not an executable API cache"}
    write_new(target / "manifest.json", json_bytes(manifest))
    verify_backup(target)
    if inventory(source) != (before, directories):
        # Immutable captured backup remains verifiable, but caller must know concurrent writes occurred.
        raise ValueError("备份发布后检测到源数据变化，请暂停写入并重新备份")
    return {"backup": str(target), **manifest, "verified": True, "api_calls": 0}


def verify_backup(path, *, include_files=False):
    path = checked_path(path)
    files, directories = inventory(path)
    if "manifest.json" not in files:
        raise ValueError("备份清单缺失或备份尚未完成")
    manifest = parse(files.pop("manifest.json"))
    if not isinstance(manifest, dict):
        raise ValueError("备份清单必须为对象")
    if manifest.get("backup_version") != BACKUP_VERSION:
        raise ValueError("备份版本不兼容")
    expected, case_names = {}, set()
    for entry in manifest["files"]:
        name = safe_relative(entry["path"])
        if name.lower() in case_names:
            raise ValueError("清单含重复路径")
        case_names.add(name.lower())
        if not (name.startswith("payload/") and allowed_data_path(name[8:]) or
                name in {"versions/" + n for n in VERSION_FILES} or
                re.fullmatch(rf"request_states/{HEX}/{HEX}\.json", name)):
            raise ValueError("清单含未审查路径")
        expected[name] = entry
    allowed_dirs = {"payload", "versions", "request_states"}
    declared_dirs = manifest["directories"]
    if len({safe_relative(d).lower() for d in declared_dirs}) != len(declared_dirs):
        raise ValueError("清单含重复目录")
    for d in declared_dirs:
        if not (d in allowed_dirs or d.startswith("payload/") and allowed_data_directory(d[8:]) or
                re.fullmatch(rf"request_states/{HEX}", d)):
            raise ValueError("清单含非法目录")
    if set(files) != set(expected) or directories != sorted(declared_dirs):
        raise ValueError("备份文件或目录缺失，或存在清单之外的文件")
    for name, data in files.items():
        if expected[name]["sha256"] != sha256(data) or expected[name]["bytes"] != len(data):
            raise ValueError("备份 SHA-256 或文件大小校验失败")
        if name.startswith("request_states/"):
            value = parse(data)
            if json_bytes(request_state(value)) != data:
                raise ValueError("请求记录违反备份字段白名单")
        if name.startswith("payload/translations/requests/"):
            if json_bytes(request_state(parse(data))) != data:
                raise ValueError("翻译请求记录违反备份字段白名单")
    if manifest["file_count"] != len(files) or manifest["total_bytes"] != sum(map(len, files.values())):
        raise ValueError("清单数量不一致")
    if manifest["annotation_request_states"] != sum(p.startswith("request_states/") for p in files):
        raise ValueError("请求状态数量不一致")
    for name in VERSION_FILES:
        if files["versions/" + name] != (BASE / name).read_bytes():
            raise ValueError("当前标签/映射/提示词版本与备份不一致，请使用匹配版本工具")
    payload = {name[8:]: data for name, data in files.items() if name.startswith("payload/")}
    counts = validate_dataset(path / "payload", payload)
    if counts != manifest["counts"]:
        raise ValueError("备份语义摘要不一致")
    if inventory(path) != ({"manifest.json": json_bytes(manifest), **files}, directories):
        # Compare original bytes rather than allowing noncanonical manifest representations.
        raise ValueError("备份校验期间文件变化或清单格式不规范")
    result = {"backup": str(path), "manifest": manifest, "verified": True, "api_calls": 0}
    return (result, files, directories) if include_files else result


def restore_backup(path, destination, *, generation=None, active_root=None):
    target = checked_path(destination)
    backup = checked_path(path)
    active = checked_path(active_root or Repository().root)
    if target.exists() or target.is_relative_to(active) or active.is_relative_to(target) or target.is_relative_to(backup) or backup.is_relative_to(target):
        raise ValueError("恢复只允许全新隔离目录，不能覆盖或嵌套活动数据/备份")
    result, files, directories = verify_backup(backup, include_files=True)
    if generation is not None:
        if not re.fullmatch(HEX, generation) or f"payload/catalog/generations/{generation}/manifest.json" not in files:
            raise ValueError("指定历史目录版本不存在")
        files = dict(files)
        files["payload/catalog/current.json"] = json_bytes({"generation_id": generation})
    # All validation has completed. Exclusive mkdir/files never overwrite anything.
    checked_path(target).mkdir(parents=True, exist_ok=False)
    for directory in directories:
        checked_path(target / directory).mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        write_new(target / name, data)
    restored, restored_dirs = inventory(target)
    if restored != files or restored_dirs != directories:
        raise ValueError("隔离恢复写入校验失败，请勿使用该目录")
    counts = validate_dataset(target / "payload", {n[8:]: d for n, d in files.items() if n.startswith("payload/")})
    repo = Repository(target / "payload")
    views = repo.manager().get_effective_tags_many(list(repo.snapshot()[0]))
    if generation is None and counts != result["manifest"]["counts"]:
        raise ValueError("恢复语义摘要与备份不一致")
    return {"destination": str(target), "restored_data_root": str(target / "payload"), "counts": counts,
            "reloaded_effective_tags": len(views), "verified": True, "api_calls": 0,
            "request_states": "只读防重放审计记录；不会自动写回实验缓存"}


def list_backups(root=None):
    folder = backup_root(root)
    if not folder.exists():
        return []
    result = []
    for path in sorted(folder.iterdir()):
        checked_path(path)
        if not path.is_dir():
            continue
        try:
            report = verify_backup(path)
            manifest = report["manifest"]
            result.append({"backup": str(path), "verified": True, "created_at": manifest["created_at"],
                           "counts": manifest["counts"], "total_bytes": manifest["total_bytes"]})
        except (ValueError, OSError, KeyError, TypeError):
            result.append({"backup": str(path), "verified": False, "status": "不完整、损坏或版本不兼容"})
    return result
