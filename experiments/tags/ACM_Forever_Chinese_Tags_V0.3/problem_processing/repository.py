"""Immutable generations and annotations; independent of experimental outputs."""
import json
import os
from copy import deepcopy
from pathlib import Path

from annotation_api.adapter import digest
from annotation_api.storage import atomic_json, now, read_jsonl
from label_pipeline import BASE, TAXONOMY
from tag_management.storage import Journal
from .adapter import normalize

PROJECT_ROOT = BASE.parents[2]


def data_root(value=None):
    value = value or os.environ.get("TAG_DATA_ROOT")
    root = Path(value) if value else PROJECT_ROOT / "data" / "labels"
    root = (PROJECT_ROOT / root).resolve() if not root.is_absolute() else root.resolve()
    if any(part.lower() in {"cache", "outputs"} for part in root.parts):
        raise ValueError("持久数据根目录不能位于 cache/outputs")
    if root.is_relative_to(PROJECT_ROOT) and not root.is_relative_to(PROJECT_ROOT / "data"):
        raise ValueError("仓库内持久数据必须放在已忽略的 data/ 下，或将 TAG_DATA_ROOT 指向仓库外")
    return root


def jsonl_write(path, rows):
    # Reuse the already tested atomic JSONL writer; no journal semantics here.
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Journal(path).write(rows)


class Repository:
    def __init__(self, root=None):
        self.root = data_root(root)
        self.pointer = self.root / "catalog" / "current.json"
        self.lock = Journal(self.root / "catalog" / "writer.jsonl")

    def current(self):
        if not self.pointer.exists():
            return None
        pointer = json.loads(self.pointer.read_text(encoding="utf-8"))
        gid = pointer["generation_id"]
        if not isinstance(gid, str) or len(gid) != 64 or any(c not in "0123456789abcdef" for c in gid):
            raise ValueError("非法目录版本")
        folder = self.root / "catalog" / "generations" / gid
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest["generation_id"] != gid or manifest["taxonomy_version"] != TAXONOMY["version"]:
            raise ValueError("目录版本不兼容")
        return folder

    def snapshot(self, folder=None):
        folder = folder or self.current()
        if folder is None:
            return {}, {}
        metadata = read_jsonl(folder / "problems.jsonl")
        labels = read_jsonl(folder / "auto_tags.jsonl")
        if digest({"problems": metadata, "auto_tags": labels}) != folder.name:
            raise ValueError("目录快照校验失败")
        return {r["problem_key"]: r for r in metadata}, {r["problem_key"]: r for r in labels}

    def import_records(self, raw_problems, annotations=()):
        from tag_management.service import auto_record
        problems = [normalize(row) for row in raw_problems]
        if len({r["problem_key"] for r in problems}) != len(problems):
            raise ValueError("导入批次包含重复题目身份")
        incoming = {p["problem_key"]: p for p in problems}
        supplied = {}
        for row in annotations:
            auto = auto_record(row)
            key = auto["problem_key"]
            if key in supplied or key not in incoming:
                raise ValueError("自动标注重复或找不到对应输入")
            if auto["content_hash"] != incoming[key]["content_hash"]:
                raise ValueError("自动标注与题面哈希不一致")
            if auto["issues"]:
                raise ValueError("只能激活有效自动标签，失败记录仍应保留在原运行历史")
            supplied[key] = deepcopy(row)
        with self.lock.locked():
            previous, labels = self.snapshot()
            for key, p in incoming.items():
                old = previous.get(key)
                if old and old["verified_content_hash"] != p["verified_content_hash"] and old["content_hash"] == p["content_hash"]:
                    raise ValueError("爬虫 content_hash 未随题面改变，拒绝静默复用旧标签")
                if old:
                    p["source_links"] = list(dict.fromkeys(old["source_links"] + p["source_links"]))
                previous[key] = p
                if key in supplied:
                    labels[key] = supplied[key]
                elif key not in labels or labels[key].get("content_hash") != p["content_hash"]:
                    base = deepcopy(p["rule_base"])
                    labels[key] = {**base, "taxonomy_version": TAXONOMY["version"],
                                   "api_call_status": "not_required" if not base["needs_ai"] else "not_called",
                                   "human_review_status": "not_reviewed", "needs_review_reason": "annotation_missing"}
            # Store original automatic annotations without changing any fields.
            history = sorted(supplied.values(), key=lambda x: x["problem_key"])
            if history:
                path = self.root / "annotations" / (digest(history) + ".jsonl")
                if path.exists():
                    if read_jsonl(path) != history:
                        raise ValueError("自动历史冲突")
                else:
                    jsonl_write(path, history)
            ps = [previous[k] for k in sorted(previous)]
            ls = [labels[k] for k in sorted(labels)]
            gid = digest({"problems": ps, "auto_tags": ls})
            folder = self.root / "catalog" / "generations" / gid
            unchanged = self.current() == folder
            if not unchanged:
                folder.mkdir(parents=True, exist_ok=True)
                # A complete existing generation is immutable; an interrupted one can be completed.
                for name, values in (("problems.jsonl", ps), ("auto_tags.jsonl", ls)):
                    path = folder / name
                    if path.exists() and read_jsonl(path) != values:
                        raise ValueError("目录历史冲突")
                    if not path.exists():
                        jsonl_write(path, values)
                if not (folder / "manifest.json").exists():
                    atomic_json(folder / "manifest.json", {"generation_id": gid, "taxonomy_version": TAXONOMY["version"],
                                                           "problem_count": len(ps), "created_at": now()})
                for name in ("annotations", "translations", "manual", "exports"):
                    self.root.joinpath(name).mkdir(parents=True, exist_ok=True)
                atomic_json(self.pointer, {"generation_id": gid})
            return {"generation_id": gid, "imported_count": len(problems), "total_count": len(ps),
                    "annotation_count": len(history), "unchanged": unchanged, "api_calls": 0}

    def manager(self, folder=None):
        from tag_management.service import TagManager
        folder = folder or self.current()
        if folder is None:
            raise ValueError("请先导入题目")
        return TagManager(folder / "auto_tags.jsonl", self.root / "manual" / "overrides.jsonl")

    def metadata_many(self, keys=None):
        from .translation import current_translation
        folder = self.current()
        if folder is None:
            raise ValueError("请先导入题目")
        problems, _ = self.snapshot(folder)
        selected = list(problems) if keys is None else list(keys)
        effective = self.manager(folder).get_effective_tags_many(selected)
        translation_index = self.root / "translations" / "current.json"
        translation_index = json.loads(translation_index.read_text(encoding="utf-8")) if translation_index.exists() else {}
        result = []
        for view in effective:
            p = deepcopy(problems[view["problem_key"]])
            p.pop("rule_base", None)
            translation = current_translation(self.root, p, index=translation_index)
            p.update(effective_tag_ids=[t["id"] for t in view["effective_tags"]], effective_tags=view["effective_tags"],
                     translated_title=translation.get("title_zh") if translation else None,
                     translated_statement=translation.get("statement_zh") if translation else None,
                     translation_status=translation.get("translation_status") if translation else "missing",
                     review_status=view["review_status"], recommendation_eligible=view["recommendation_eligible"],
                     translation_rights_status="unknown", display_requires_rights_check=True)
            result.append(p)
        return result

    def export(self, path=None):
        rows = self.metadata_many()
        path = Path(path).resolve() if path else self.root / "exports" / (digest(rows) + ".jsonl")
        if not path.is_relative_to(self.root / "exports"):
            raise ValueError("导出只能写入持久根目录的 exports，不能覆盖输入或原预测")
        if path.exists():
            if read_jsonl(path) != rows:
                raise ValueError("导出已存在且内容不同，请使用新文件名")
        else:
            jsonl_write(path, rows)
        return {"path": str(path.resolve()), "count": len(rows)}
