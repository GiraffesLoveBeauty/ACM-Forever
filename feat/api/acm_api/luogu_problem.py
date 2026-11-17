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


def canonical_problem_id(value):
    """Resolve historical P-problem aliases without changing stored records."""
    if isinstance(value, str):
        value = value.strip()
        if value[:6].casefold() == "luogu_":
            value = value[6:]
    return problem_id(value)


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
        if text is None:
            text = ""
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


def _classification_metadata_sql(problem_id):
    """Use one classification source for filtering and display without rewriting aliases."""
    return ("(SELECT lg.metadata_json FROM crawler_problems lg WHERE lg.platform='luogu' "
            f"AND lg.problem_id COLLATE NOCASE IN ({problem_id},'luogu_'||{problem_id}) "
            "ORDER BY CASE WHEN lg.problem_id GLOB 'P*' THEN 0 "
            "WHEN lg.problem_id GLOB 'p*' THEN 1 ELSE 2 END,lg.updated_at DESC,lg.problem_id LIMIT 1)")


async def attach_classifications(db, items, *, indexed=False):
    luogu = [item for item in items if item.get("platform") == "luogu"]
    if not luogu:
        return
    for item in luogu:
        try:
            pid = canonical_problem_id(item["problem_id"])
        except ValueError:
            continue  # Keep unsupported historical IDs intact.
        item["problem_id"] = pid
        item["problem_url"] = ORIGIN + "/problem/" + pid
    taxonomy = await load_taxonomy(db)
    ids = list({item["problem_id"] for item in luogu})
    marks = ",".join("(?)" for _ in ids)
    if indexed:
        natives = {}
        async with db.execute(f"WITH ids(problem_id) AS (VALUES {marks}) "
                              "SELECT p.id_key,p.native_difficulty,t.tag_id FROM ids "
                              "JOIN problem_listing p ON p.platform='luogu' AND p.id_key=ids.problem_id "
                              "LEFT JOIN problem_listing_native_tags t ON t.platform=p.platform AND t.id_key=p.id_key "
                              "ORDER BY p.id_key,t.position,t.tag_id", ids) as cursor:
            for row in await cursor.fetchall():
                native = natives.setdefault(row["id_key"], {"difficulty": row["native_difficulty"], "tag_ids": []})
                if row["tag_id"] is not None:
                    native["tag_ids"].append(row["tag_id"])
    else:
        source = _classification_metadata_sql("ids.problem_id")
        async with db.execute(f"WITH ids(problem_id) AS (VALUES {marks}) "
                              f"SELECT problem_id,{source} AS metadata_json FROM ids", ids) as cursor:
            natives = {row["problem_id"]: json.loads(row["metadata_json"] or "{}").get("luogu", {})
                       for row in await cursor.fetchall()}
    for item in luogu:
        native = natives.get(item["problem_id"], {})
        item["native_difficulty"], item["native_tags"] = classifications(native, taxonomy)
        item["classification_source"] = "luogu"
        item["problem_rating"] = None


async def native_filter(db, args, platform, *, indexed=False):
    """Native IDs/ranges and tag intersections, before counting or pagination."""
    names = ("native_difficulty", "native_difficulty_min", "native_difficulty_max", "native_tag", "native_tags")
    supplied = {key: args.get(key) for key in names if args.get(key) is not None}
    if not supplied:
        return "", []
    if platform != "luogu":
        raise ValueError("原生难度/标签须指定 platform=luogu")
    def ident(text, *, difficulty=False):
        if not isinstance(text, str) or not re.fullmatch(r"-?[0-9]{1,9}", text) or difficulty and int(text) < 0:
            raise ValueError("原生难度/标签须使用有效整数 ID")
        return int(text)
    exact = supplied.get("native_difficulty")
    bounds = {key: ident(supplied[key], difficulty=True) for key in ("native_difficulty_min", "native_difficulty_max") if key in supplied}
    if exact is not None and bounds:
        raise ValueError("单个难度与难度区间不能同时使用")
    levels = {ident(exact, difficulty=True)} if exact is not None else None
    if bounds:
        taxonomy = await load_taxonomy(db)
        order = [level["id"] for level in (taxonomy or {}).get("difficulties", []) if level["id"] != 0]
        if not order or any(value not in order for value in bounds.values()):
            raise ValueError("难度区间须使用已同步的原生等级；暂无评定请单独选择")
        start = order.index(bounds["native_difficulty_min"]) if "native_difficulty_min" in bounds else 0
        end = order.index(bounds["native_difficulty_max"]) if "native_difficulty_max" in bounds else len(order)-1
        if start > end:
            raise ValueError("原生难度上限不能低于下限")
        levels = set(order[start:end+1])
    tags = set()
    if "native_tag" in supplied:
        tags.add(ident(supplied["native_tag"]))
    if "native_tags" in supplied:
        values = supplied["native_tags"].split(",")
        if not 1 <= len(values) <= 20:
            raise ValueError("最多选择 20 个洛谷原生标签")
        tags.update(ident(value) for value in values)
    if len(tags) > 20:
        raise ValueError("最多选择 20 个洛谷原生标签")
    params = []
    alias = "p" if indexed else "ln"
    filters = []
    if levels is not None:
        filters.append(alias + ".native_difficulty IN (" + ",".join("?" for _ in levels) + ")")
        params.extend(sorted(levels))
    for tag in sorted(tags):
        filters.append(f"EXISTS(SELECT 1 FROM problem_listing_native_tags nt WHERE nt.platform={alias}.platform AND nt.id_key={alias}.id_key AND nt.tag_id=?)")
        params.append(tag)
    condition = " AND ".join(filters) or "1=1"
    if indexed:
        return " AND " + condition, params
    from .problem_tracker import problem_id_key
    await db.create_function("problem_id_key", 2, problem_id_key, deterministic=True)
    return (" AND EXISTS(SELECT 1 FROM problem_listing ln WHERE ln.platform=p.platform "
            "AND ln.id_key=problem_id_key(p.platform,p.problem_id) AND " + condition + ")", params)
