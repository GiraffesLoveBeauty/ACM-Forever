"""Read a member's contest progress from the local catalog and submission evidence."""

import json
import re
from urllib.parse import urlsplit

from .cf_client import problem_url as cf_problem_url
from .problem_tags import has_problem_tag, problem_tags


PLATFORMS = {"codeforces", "atcoder"}
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{1,160}")
CF_PROBLEM_ID = re.compile(r"(?:cf_)?([1-9][0-9]*)(?:-?([A-Za-z]+[0-9]*))?", re.IGNORECASE | re.ASCII)


def tracker_options(args):
    platform = args.get("platform", "")
    scope = args.get("scope", "all")
    state = args.get("state", "")
    tag = args.get("tag", "")
    problem_tag = args.get("problem_tag", "")
    if platform and platform not in PLATFORMS:
        raise ValueError("比赛进度目前支持 Codeforces 和 AtCoder。")
    if scope not in {"all", "solved"} or state not in {"", "favorite"}:
        raise ValueError("无效的题目范围或收藏筛选。")
    if len(tag) > 100:
        raise ValueError("搜索内容最多 100 个字符。")
    if len(problem_tag) > 100:
        raise ValueError("题目标签最多 100 个字符。")
    values = {}
    for key, default, maximum in (("page", "1", 1000000), ("page_size", "20", 50)):
        raw = args.get(key, default)
        if not re.fullmatch(r"[0-9]+", raw) or not 1 <= int(raw) <= maximum:
            raise ValueError(f"{key} 必须为 1–{maximum} 的整数。")
        values[key] = int(raw)
    return {"platform": platform, "scope": scope, "state": state, "tag": tag.strip().casefold(),
            "problem_tag": problem_tag.strip(), **values}


def natural_key(value):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", str(value)) if part)


def identity(platform, problem_id, contest_id=None, problem_index=None, problem_url=None):
    """Prefer persisted contest metadata/URLs; task prefixes are not always contest IDs."""
    if platform not in PLATFORMS or not isinstance(problem_id, str) or not SAFE_ID.fullmatch(problem_id):
        return None
    contest = str(contest_id or "")
    index = str(problem_index or "")
    if platform == "codeforces":
        id_match = CF_PROBLEM_ID.fullmatch(problem_id)
        if not contest or not index:
            try:
                parts = urlsplit(problem_url or "")
                match = re.fullmatch(r"/(?:contest|gym)/(\d+)/problem/([A-Za-z]+\d*|\d+)/?", parts.path)
                if match is None:
                    match = re.fullmatch(r"/problemset/problem/(\d+)/([A-Za-z]+\d*|\d+)/?", parts.path)
            except ValueError:
                match = None
            if match:
                contest, index = match.groups()
            elif id_match:
                id_contest, id_index = id_match.groups()
                if contest and id_contest.startswith(contest):
                    # Numeric Gym indices require a known contest boundary.
                    index = id_contest[len(contest):] + (id_index or "")
                elif id_index is not None:
                    contest, index = id_contest, id_index
        if not re.fullmatch(r"[1-9]\d{0,6}", contest) or not re.fullmatch(r"[A-Za-z]+\d*|\d+", index):
            return None
        index = index.upper()
        return "cf_" + contest + index, contest, index
    if not contest or not index:
        try:
            parts = urlsplit(problem_url or "")
            match = re.fullmatch(r"/contests/([A-Za-z0-9_-]+)/tasks/([A-Za-z0-9_-]+)/?", parts.path)
        except ValueError:
            match = None
        if match and match[2] == problem_id:
            contest = match[1]
        if not contest:
            contest, _, index = problem_id.rpartition("_")
        if not index:
            index = problem_id.rpartition("_")[2]
    if not contest or not SAFE_ID.fullmatch(contest):
        return None
    return problem_id, contest, index.upper()


def problem_id_aliases(platform, problem_id):
    """Recognize compact, prefixed, and legacy hyphenated CF IDs."""
    aliases = [problem_id]
    if platform == "codeforces":
        match = CF_PROBLEM_ID.fullmatch(problem_id)
        if match:
            contest, index = match.groups()
            bare = contest + (index or "")
            aliases.extend((bare, "cf_" + bare))
            if index is not None:
                legacy = contest + "-" + index
                aliases.extend((legacy, "cf_" + legacy))
    return tuple(dict.fromkeys(aliases))


def problem_id_key(platform, problem_id):
    """Group the same aliases accepted by CF detail lookups; keep other IDs exact."""
    if platform != "codeforces":
        return problem_id
    match = CF_PROBLEM_ID.fullmatch(problem_id)
    if match:
        contest, index = match.groups()
        return "CF_" + contest + (index or "").upper()
    return problem_id.upper()


def rating(value):
    try:
        return int(value) if value is not None and str(value).strip() else None
    except (ValueError, TypeError):
        return None


async def attempt_problem_metadata(db, owner, platform, problem_id):
    """Resolve an attempt-only link from this account, without publishing a catalog row."""
    if not owner or platform not in PLATFORMS or not SAFE_ID.fullmatch(problem_id):
        return None
    aliases = problem_id_aliases(platform, problem_id)
    wanted = problem_id_key(platform, problem_id)
    comparison = "problem_id COLLATE NOCASE" if platform == "codeforces" else "problem_id"
    async with db.execute(
        "SELECT problem_id,contest_id FROM submission_attempts WHERE owner_qq_id=? AND platform=? AND "
        + comparison + " IN (" + ",".join("?" for _ in aliases) + ") ORDER BY submitted_at DESC,id DESC",
        (owner, platform, *aliases),
    ) as cursor:
        async for row in cursor:
            parsed = identity(platform, row["problem_id"], row["contest_id"])
            if parsed is None or problem_id_key(platform, parsed[0]) != wanted:
                continue
            pid, contest, index = parsed
            url = (cf_problem_url(contest, index) if platform == "codeforces" else
                   f"https://atcoder.jp/contests/{contest}/tasks/{pid}")
            return {"problem_id": pid, "contest_id": contest, "problem_name": pid,
                    "problem_rating": None, "problem_url": url, "tags": ""}
    return None


async def contest_tracker(db, owner, options):
    """Group complete local contests before filtering/paging; never perform network I/O."""
    catalog = {}
    aliases = {}
    async with db.execute("SELECT platform,contest_id,contest_name,start_time FROM crawler_contests") as cursor:
        contest_info = {(row["platform"], row["contest_id"]): dict(row) for row in await cursor.fetchall()}

    def add(row):
        alias_key = (row["platform"], problem_id_key(row["platform"], row["problem_id"]))
        key = aliases.get(alias_key)
        if key is None:
            parsed = identity(row["platform"], row["problem_id"], row.get("contest_id"),
                              row.get("problem_index"), row.get("problem_url"))
            if parsed is None:
                return None
            pid, contest, index = parsed
            key = row["platform"], pid
            aliases[alias_key] = key
            aliases[row["platform"], problem_id_key(row["platform"], pid)] = key
        if key in catalog:
            problem = catalog[key]
            if problem["problem_rating"] is None:
                problem["problem_rating"] = rating(row.get("problem_rating"))
            if problem["problem_name"] == problem["problem_id"] and row.get("problem_name"):
                problem["problem_name"] = row["problem_name"]
            if not problem_tags(problem["tags"]) and problem_tags(row.get("tags")):
                problem["tags"] = row["tags"]
            return problem
        contest_name = None
        try:
            metadata = json.loads(row.get("metadata_json") or "{}")
            if isinstance(metadata, dict) and isinstance(metadata.get("contest_name"), str):
                contest_name = metadata["contest_name"].strip()[:300] or None
        except (ValueError, TypeError):
            pass
        catalog[key] = {"platform": row["platform"], "problem_id": pid, "contest_id": contest,
                        "problem_index": index, "problem_name": row.get("problem_name") or pid,
                        "problem_rating": rating(row.get("problem_rating")),
                        "tags": row.get("tags") or "", "contest_name": contest_name,
                        "status": "unseen", "ac_at": None, "last_submit_at": None,
                        "is_favorite": False}
        return catalog[key]

    async with db.execute(
        "SELECT platform,problem_id,contest_id,problem_index,problem_name,problem_rating,problem_url,tags,metadata_json "
        "FROM crawler_problems WHERE platform IN ('codeforces','atcoder') ORDER BY problem_id"
    ) as cursor:
        for row in await cursor.fetchall():
            add(dict(row))
    async with db.execute(
        "SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations "
        "WHERE platform IN ('codeforces','atcoder') ORDER BY problem_id"
    ) as cursor:
        for row in await cursor.fetchall():
            add(dict(row))
    async with db.execute(
        "SELECT platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time "
        "FROM submissions WHERE user_qq_id=? AND platform IN ('codeforces','atcoder') "
        "ORDER BY submit_time DESC,problem_id", (owner,)
    ) as cursor:
        for row in await cursor.fetchall():
            problem = add(dict(row))
            if problem:
                problem["status"] = "solved"
                problem["ac_at"] = max(problem["ac_at"] or 0, row["submit_time"])
                problem["last_submit_at"] = max(problem["last_submit_at"] or 0, row["submit_time"])
    async with db.execute(
        "SELECT platform,problem_id,contest_id,MAX(submitted_at) AS last_submit_at,"
        "MAX(CASE WHEN UPPER(TRIM(verdict)) IN ('OK','AC','ACCEPTED') THEN submitted_at END) AS ac_at "
        "FROM submission_attempts WHERE owner_qq_id=? AND platform IN ('codeforces','atcoder') "
        "GROUP BY platform,problem_id,contest_id", (owner,)
    ) as cursor:
        for row in await cursor.fetchall():
            problem = add(dict(row))
            if not problem:
                continue
            problem["last_submit_at"] = max(problem["last_submit_at"] or 0, row["last_submit_at"])
            if row["ac_at"] is not None:
                problem["status"] = "solved"
                problem["ac_at"] = max(problem["ac_at"] or 0, row["ac_at"])
            elif problem["status"] != "solved":
                problem["status"] = "attempted"
    async with db.execute(
        "SELECT platform,problem_id FROM user_problem_state WHERE owner_qq_id=? AND is_favorite=1 "
        "AND platform IN ('codeforces','atcoder')", (owner,)
    ) as cursor:
        for row in await cursor.fetchall():
            parsed = identity(row["platform"], row["problem_id"])
            key = aliases.get((row["platform"], problem_id_key(row["platform"], row["problem_id"])),
                              (row["platform"], parsed[0] if parsed else row["problem_id"]))
            if key in catalog:
                catalog[key]["is_favorite"] = True

    contests = {}
    for problem in catalog.values():
        platform = problem["platform"]
        if options["platform"] and platform != options["platform"]:
            continue
        contest_id = problem["contest_id"]
        info = contest_info.get((platform, contest_id), {})
        group = contests.setdefault((platform, contest_id), {
            "platform": platform, "contest_id": contest_id,
            "contest_name": info.get("contest_name") or problem["contest_name"] or (f"Codeforces #{contest_id}" if platform == "codeforces" else f"AtCoder {contest_id}"),
            "start_time": info.get("start_time"),
            "problems": [],
        })
        group["problems"].append(problem)

    keyword = options["tag"]
    cf_search_key = problem_id_key("codeforces", keyword) if CF_PROBLEM_ID.fullmatch(keyword) else None

    def matches(problem, group):
        if options["scope"] == "solved" and problem["status"] != "solved":
            return False
        if options["state"] == "favorite" and not problem["is_favorite"]:
            return False
        if options.get("problem_tag") and not has_problem_tag(problem["tags"], options["problem_tag"]):
            return False
        if (cf_search_key is not None and problem["platform"] == "codeforces"
                and cf_search_key == problem_id_key("codeforces", problem["problem_id"])):
            return True
        return not keyword or keyword in " ".join(
            str(value) for value in (problem["problem_id"], problem["problem_name"], problem["tags"],
                                    group["contest_id"], group["contest_name"])).casefold()

    result = []
    for group in contests.values():
        if not any(matches(problem, group) for problem in group["problems"]):
            continue
        group["problems"].sort(key=lambda item: (natural_key(item["problem_index"]), item["problem_id"]))
        group["total_count"] = len(group["problems"])
        group["solved_count"] = sum(problem["status"] == "solved" for problem in group["problems"])
        group["attempted_count"] = sum(problem["status"] == "attempted" for problem in group["problems"])
        for problem in group["problems"]:
            problem.pop("tags")
            problem.pop("contest_name")
        result.append(group)
    result.sort(key=lambda item: (item["start_time"] is not None, item["start_time"] or 0,
                                  item["platform"], natural_key(item["contest_id"])), reverse=True)
    start = (options["page"] - 1) * options["page_size"]
    return {"items": result[start:start + options["page_size"]], "total": len(result),
            "page": options["page"], "page_size": options["page_size"]}
