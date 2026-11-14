"""Luogu P-problem normalization, safe Markdown and local native classifications."""

import hashlib
import html
import json
import re
import time
from urllib.parse import urljoin, urlsplit

import mistune

from .luogu_client import ORIGIN, page_context
from .problem_content import TreeParser

TAXONOMY_TTL = 86400
SECTIONS = (("background", "题目背景"), ("description", "题目描述"),
            ("formatI", "输入格式"), ("formatO", "输出格式"), ("hint", "说明与提示"))


def problem_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"P[1-9][0-9]{0,8}", value.strip(), re.I):
        raise ValueError("洛谷题号必须为 P 加正整数，例如 P1001；本期仅采集公开 P 题库")
    return value.strip().upper()


def _integer(value, label, *, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ValueError(f"洛谷 {label} 格式异常")
    return value


def normalize_taxonomy(config, tags):
    if not isinstance(config, dict) or not isinstance(tags, dict):
        raise ValueError("洛谷分类字典格式异常")
    result = {"difficulties": [], "tags": [], "tag_types": [],
              "versions": {"config": config.get("_version"), "tags": tags.get("_version")}}
    for source, key in ((config.get("ProblemDifficulty"), "difficulties"),
                        (tags.get("types"), "tag_types"), (tags.get("tags"), "tags")):
        if not isinstance(source, list) or not source:
            raise ValueError("洛谷分类字典缺少难度、标签或类别")
        seen = set()
        for item in source:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                raise ValueError("洛谷分类字典条目格式异常")
            ident = _integer(item.get("id"), "分类 ID")
            if ident in seen:
                raise ValueError("洛谷分类字典包含重复 ID")
            seen.add(ident)
            entry = {"id": ident, "name": item["name"]}
            if key == "tags":
                entry["type"] = _integer(item.get("type"), "标签类别")
                entry["parent"] = None if item.get("parent") is None else _integer(item["parent"], "标签父级")
            else:
                for field in ("type", "color", "order"):
                    if field in item:
                        entry[field] = item[field]
            result[key].append(entry)
    return result


async def load_taxonomy(db):
    async with db.execute("SELECT data_json,updated_at FROM crawler_platform_taxonomies WHERE platform='luogu'") as cursor:
        row = await cursor.fetchone()
    if not row:
        return None
    data = json.loads(row["data_json"])
    return {**data, "platform": "luogu", "updated_at": row["updated_at"],
            "stale": int(time.time()) - row["updated_at"] >= TAXONOMY_TTL}


async def save_taxonomy(db, taxonomy):
    await db.execute("INSERT INTO crawler_platform_taxonomies(platform,data_json,updated_at) VALUES('luogu',?,?) "
                     "ON CONFLICT(platform) DO UPDATE SET data_json=excluded.data_json,updated_at=excluded.updated_at",
                     (json.dumps(taxonomy, ensure_ascii=False), int(time.time())))
    await db.commit()


def classifications(native, taxonomy):
    taxonomy = taxonomy or {}
    difficulties = {row["id"]: row for row in taxonomy.get("difficulties", [])}
    tags = {row["id"]: row for row in taxonomy.get("tags", [])}
    types = {row["id"]: row for row in taxonomy.get("tag_types", [])}
    difficulty_id = native.get("difficulty")
    difficulty = {"id": difficulty_id, "name": None, "color": None, **difficulties.get(difficulty_id, {})}
    result = []
    for ident in native.get("tag_ids", []):
        tag = {"id": ident, "name": None, "type": None, "parent": None, **tags.get(ident, {})}
        tag["category"] = types.get(tag["type"])
        result.append(tag)
    return difficulty, result


def metadata(value, taxonomy):
    if not isinstance(value, dict) or value.get("type") != "P":
        raise ValueError("洛谷目录含非公开 P 题库条目")
    pid = problem_id(value.get("pid"))
    name = value.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("洛谷题目缺少名称")
    level = None if value.get("difficulty") is None else _integer(value["difficulty"], "难度", minimum=0)
    ids = value.get("tags")
    if not isinstance(ids, list) or any(type(ident) is not int for ident in ids):
        raise ValueError("洛谷标签 ID 格式异常")
    native = {"difficulty": level, "tag_ids": list(dict.fromkeys(ids)), "type": "P",
              "taxonomy_versions": (taxonomy or {}).get("versions", {})}
    for field in ("fullScore", "totalSubmit", "totalAccepted"):
        if field in value:
            native[field] = _integer(value[field], field, minimum=0)
    _, labels = classifications(native, taxonomy)
    return {"platform": "luogu", "problem_id": pid, "contest_id": "", "problem_index": None,
            "problem_name": name.strip(), "problem_rating": None, "problem_url": ORIGIN + "/problem/" + pid,
            "tags": [label["name"] or f"#{label['id']}" for label in labels], "luogu": native}


def catalog_page(raw, taxonomy):
    data = page_context(raw, template="problem.list")["data"].get("problems")
    if not isinstance(data, dict) or not isinstance(data.get("result"), list):
        raise ValueError("洛谷题目目录结构异常")
    count = _integer(data.get("count"), "目录总数", minimum=0)
    per_page = _integer(data.get("perPage"), "目录分页大小", minimum=1)
    if count > 500000 or per_page > 1000 or len(data["result"]) > per_page:
        raise ValueError("洛谷题目目录大小异常")
    return [metadata(item, taxonomy) for item in data["result"]], count, per_page


class _Renderer(mistune.HTMLRenderer):
    def __init__(self, source_url):
        super().__init__(escape=True)
        self.source_url = source_url

    def _url(self, value):
        value = urljoin(self.source_url, value)
        parsed = urlsplit(value)
        return value if parsed.scheme in ("http", "https") and parsed.hostname else None

    def link(self, text, url, title=None):
        safe = self._url(url)
        return super().link(text, safe, title) if safe else text

    def image(self, text, url, title=None):
        safe = self._url(url)
        return super().image(text, safe, title) if safe else html.escape(text)


def render_markdown(source, source_url=ORIGIN + "/"):
    # Separate safe renderer; forum attachment discovery has different needs.
    renderer = _Renderer(source_url)
    md = mistune.create_markdown(renderer=renderer, plugins=["table", "strikethrough", "math"])
    renderer.register("inline_math", lambda renderer, text: '<span class="math">\\(' + html.escape(text) + '\\)</span>')
    renderer.register("block_math", lambda renderer, text: '<div class="math">$$\n' + html.escape(text) + '\n$$</div>\n')
    return md(source)


def parse_problem(raw, expected_id, taxonomy):
    value = page_context(raw, template="problem.show")["data"].get("problem")
    item = metadata(value, taxonomy)
    if item["problem_id"] != problem_id(expected_id):
        raise ValueError("洛谷返回的题号与请求不一致")
    body = value.get("content")
    if not isinstance(body, dict):
        raise ValueError("洛谷页面缺少 Markdown 题面")
    if body.get("locale") not in (None, "zh-CN"):
        raise ValueError("洛谷题面语言异常")
    parts, sections = [], {}
    for key, title in SECTIONS:
        text = body.get(key, "")
        if not isinstance(text, str):
            raise ValueError("洛谷 Markdown 段落格式异常")
        sections[key] = text
        if text.strip():
            parts.append("## " + title + "\n\n" + text)
    if not sections["description"].strip():
        raise ValueError("洛谷题目描述为空，保留已有题面")
    if not isinstance(value.get("samples"), list):
        raise ValueError("洛谷样例字段缺失或格式异常")
    samples = []
    for index, pair in enumerate(value["samples"], 1):
        if not isinstance(pair, list) or len(pair) != 2 or any(not isinstance(text, str) for text in pair):
            raise ValueError("洛谷样例输入输出不完整")
        samples.append({"index": index, "input": pair[0], "output": pair[1]})
    limits = value.get("limits")
    if limits is not None:
        if not isinstance(limits, dict):
            raise ValueError("洛谷时间或内存限制格式异常")
        for key in ("time", "memory"):
            values = limits.get(key)
            if values is not None and (not isinstance(values, list) or any(type(v) is not int or v < 0 for v in values)):
                raise ValueError("洛谷时间或内存限制格式异常")
    markdown = "\n\n".join(parts)
    rendered = render_markdown(markdown, item["problem_url"])
    parser = TreeParser()
    parser.feed(rendered)
    item["luogu"].update(markdown=markdown, sections=sections, limits=limits, locale="zh-CN")
    content = {"statement_html": rendered, "statement_text": parser.root.text(blocks=True).strip(),
               "statement_language": "zh-CN", "requested_language": "zh-CN", "samples": samples,
               "source_url": item["problem_url"], "sha256": hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()}
    return item, content


async def attach_classifications(db, items):
    luogu = [item for item in items if item.get("platform") == "luogu"]
    if not luogu:
        return
    taxonomy = await load_taxonomy(db)
    ids = list({item["problem_id"] for item in luogu})
    marks = ",".join("?" for _ in ids)
    async with db.execute("SELECT problem_id,metadata_json FROM crawler_problems WHERE platform='luogu' "
                          f"AND problem_id IN ({marks})", ids) as cursor:
        natives = {row["problem_id"]: json.loads(row["metadata_json"]).get("luogu", {}) for row in await cursor.fetchall()}
    for item in luogu:
        native = natives.get(item["problem_id"], {})
        item["native_difficulty"], item["native_tags"] = classifications(native, taxonomy)
        item["classification_source"] = "luogu"
        item["problem_rating"] = None


async def native_filter(db, args, platform):
    """Apply before pagination/counting; native IDs never mean CF ratings."""
    filters = []
    params = []
    for key, field in (("native_difficulty", "difficulty"), ("native_tag", "tag_ids")):
        text = args.get(key)
        if text is None:
            continue
        if platform != "luogu" or not re.fullmatch(r"-?[0-9]{1,9}", text) or (field == "difficulty" and int(text) < 0):
            raise ValueError("原生难度/标签须指定 platform=luogu，并使用整数 ID")
        value = int(text)
        def match(raw, expected, field=field):
            native = json.loads(raw).get("luogu", {})
            return int(expected in native.get(field, []) if field == "tag_ids" else native.get(field) == expected)
        function = "luogu_match_" + field
        await db.create_function(function, 2, match, deterministic=True)
        filters.append(f"EXISTS(SELECT 1 FROM crawler_problems lg WHERE lg.platform='luogu' AND p.platform=lg.platform "
                       f"AND p.problem_id=lg.problem_id AND {function}(lg.metadata_json,?)=1)")
        params.append(value)
    return "".join(" AND " + clause for clause in filters), params
