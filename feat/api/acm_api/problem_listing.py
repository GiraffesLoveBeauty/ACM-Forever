"""Filter before count/pagination and order by explicitly identified time."""
import re
from .problem_time import time_options
from .problem_tracker import problem_id_key


async def listing_query(db, base, params, args, platform):
    await db.create_function("problem_id_key", 2, problem_id_key, deterministic=True)
    def numeric_rating(value):
        text = str(value) if value is not None else ""
        return int(text) if re.fullmatch(r"[0-9]{1,6}", text) else None
    await db.create_function("problem_rating_number", 1, numeric_rating, deterministic=True)
    await db.create_function("public_luogu_problem", 1, lambda value: int(bool(re.fullmatch(r"P[1-9][0-9]{0,8}", problem_id_key("luogu", value)))), deterministic=True)
    query = """SELECT p.*,t.source_time,t.first_seen_at,
        COALESCE(t.source_time,t.first_seen_at) AS problem_time,
        CASE WHEN t.source_time IS NOT NULL THEN 'contest'
             WHEN t.first_seen_at IS NOT NULL THEN 'first_seen' ELSE 'unknown' END AS time_basis
        FROM (""" + base + """) p LEFT JOIN (
          SELECT c.platform,problem_id_key(c.platform,c.problem_id) AS id_key,
                 MIN(CAST(strftime('%s',c.created_at) AS INTEGER)) AS first_seen_at,
                 MAX(CASE WHEN c.platform<>'luogu' AND d.start_time>0 THEN d.start_time END) AS source_time
          FROM crawler_problems c LEFT JOIN crawler_contests d
          ON d.platform=c.platform AND d.contest_id=c.contest_id
          GROUP BY c.platform,problem_id_key(c.platform,c.problem_id)
        ) t ON t.platform=p.platform AND t.id_key=problem_id_key(p.platform,p.problem_id) WHERE (p.platform<>'luogu' OR public_luogu_problem(p.problem_id)=1)"""
    values = list(params)
    bounds = {}
    for key in ("rating_min", "rating_max"):
        text = args.get(key)
        if text in (None, ""):
            continue
        if platform not in {"codeforces", "atcoder"} or not str(text).isdigit() or not 0 <= int(text) <= 100000:
            raise ValueError("数值难度范围须指定 CF/AtCoder，使用 0–100000 的整数")
        bounds[key] = int(text)
    if bounds.get("rating_min", 0) > bounds.get("rating_max", 100000):
        raise ValueError("难度上限不能小于下限")
    if bounds:
        query += " AND problem_rating_number(p.problem_rating) IS NOT NULL"
        for key, operator in (("rating_min", ">="), ("rating_max", "<=")):
            if key in bounds:
                query += " AND problem_rating_number(p.problem_rating)" + operator + "?"
                values.append(bounds[key])
    times = time_options(args, platform)
    if times:
        column = {"contest": "t.source_time", "first_seen": "t.first_seen_at", "auto": "COALESCE(t.source_time,t.first_seen_at)"}[times["time_basis"]]
        for key, operator in (("start_at", ">="), ("end_at", "<")):
            if key in times:
                query += " AND " + column + operator + "?"
                values.append(times[key])
    return query, values


NEWEST_ORDER = " ORDER BY problem_time IS NULL,problem_time DESC,p.platform,problem_id_key(p.platform,p.problem_id),p.problem_id"
