"""Indexed, rebuildable read model of the existing problem catalog and member state.

The source tables remain authoritative. Pure-SQL change queues accept writes from
legacy/offline connections too; service connections drain them in the same commit.
No read request rebuilds or merges the submissions of all members.
"""
import json
import re
import secrets
import sqlite3
import time

from .problem_time import time_options
from .problem_tracker import problem_id_aliases, problem_id_key
from .problem_tags import problem_tags, selected_problem_tag_keys


_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS problem_listing (
        platform TEXT NOT NULL,id_key TEXT NOT NULL,problem_id TEXT NOT NULL,
        problem_name TEXT,problem_rating,problem_url TEXT,tags TEXT NOT NULL,
        rating_number INTEGER,source_time INTEGER,first_seen_at INTEGER NOT NULL,
        sort_unknown INTEGER NOT NULL,sort_order INTEGER NOT NULL,
        native_difficulty INTEGER,is_public INTEGER NOT NULL,
        PRIMARY KEY(platform,id_key))""",
    "CREATE INDEX IF NOT EXISTS idx_listing_newest ON problem_listing(is_public,sort_unknown,sort_order,platform,id_key)",
    "CREATE INDEX IF NOT EXISTS idx_listing_platform_newest ON problem_listing(platform,is_public,sort_unknown,sort_order,id_key)",
    "CREATE INDEX IF NOT EXISTS idx_listing_rating ON problem_listing(platform,rating_number,id_key)",
    "CREATE INDEX IF NOT EXISTS idx_listing_source_time ON problem_listing(platform,source_time,id_key)",
    "CREATE INDEX IF NOT EXISTS idx_listing_first_seen ON problem_listing(platform,first_seen_at,id_key)",
    "CREATE INDEX IF NOT EXISTS idx_listing_native_difficulty ON problem_listing(platform,native_difficulty,id_key)",
    """CREATE TABLE IF NOT EXISTS problem_listing_tags (
        platform TEXT NOT NULL,id_key TEXT NOT NULL,tag_key TEXT NOT NULL,tag TEXT NOT NULL,
        PRIMARY KEY(platform,id_key,tag_key))""",
    "CREATE INDEX IF NOT EXISTS idx_listing_tag_lookup ON problem_listing_tags(tag_key,platform,id_key,tag)",
    "CREATE INDEX IF NOT EXISTS idx_listing_tag_names ON problem_listing_tags(platform,tag_key,tag)",
    """CREATE TABLE IF NOT EXISTS problem_listing_tag_options (
        platform TEXT NOT NULL,tag_key TEXT NOT NULL,tag TEXT NOT NULL,uses INTEGER NOT NULL,
        PRIMARY KEY(platform,tag_key))""",
    """CREATE TABLE IF NOT EXISTS problem_listing_native_tags (
        platform TEXT NOT NULL,id_key TEXT NOT NULL,tag_id INTEGER NOT NULL,position INTEGER NOT NULL,
        PRIMARY KEY(platform,id_key,tag_id))""",
    "CREATE INDEX IF NOT EXISTS idx_listing_native_tag ON problem_listing_native_tags(tag_id,platform,id_key)",
    """CREATE TABLE IF NOT EXISTS member_problem_index (
        owner TEXT NOT NULL,platform TEXT NOT NULL,id_key TEXT NOT NULL,
        ac_at INTEGER,ac_order INTEGER,own_tags TEXT NOT NULL,
        is_favorite INTEGER NOT NULL,outside_inbox INTEGER NOT NULL,
        PRIMARY KEY(owner,platform,id_key))""",
    "CREATE INDEX IF NOT EXISTS idx_member_ac_page ON member_problem_index(owner,ac_order,platform,id_key) WHERE ac_at IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_member_platform_ac_page ON member_problem_index(owner,platform,ac_order,id_key) WHERE ac_at IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_member_favorite ON member_problem_index(owner,platform,id_key) WHERE is_favorite=1",
    """CREATE TABLE IF NOT EXISTS member_problem_tags (
        owner TEXT NOT NULL,platform TEXT NOT NULL,id_key TEXT NOT NULL,
        tag_key TEXT NOT NULL,tag TEXT NOT NULL,PRIMARY KEY(owner,platform,id_key,tag_key))""",
    "CREATE INDEX IF NOT EXISTS idx_member_tag_lookup ON member_problem_tags(owner,tag_key,platform,id_key,tag)",
    "CREATE TABLE IF NOT EXISTS problem_listing_dirty(platform TEXT NOT NULL,problem_id TEXT NOT NULL,PRIMARY KEY(platform,problem_id))",
    "CREATE TABLE IF NOT EXISTS member_problem_dirty(owner TEXT NOT NULL,platform TEXT NOT NULL,problem_id TEXT NOT NULL,PRIMARY KEY(owner,platform,problem_id))",
    "CREATE INDEX IF NOT EXISTS idx_submissions_catalog_identity ON submissions(platform,problem_id COLLATE NOCASE,submit_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_submissions_member_identity ON submissions(user_qq_id,platform,problem_id COLLATE NOCASE,submit_time DESC)",
    "CREATE INDEX IF NOT EXISTS idx_recommendations_identity ON recommendations(platform,problem_id COLLATE NOCASE)",
    "CREATE INDEX IF NOT EXISTS idx_problem_state_identity ON user_problem_state(owner_qq_id,platform,problem_id COLLATE NOCASE)",
)


async def initialize_listing(db):
    """One transactional, idempotent backfill; never invoked by a list request."""
    async with db.execute("SELECT value FROM settings WHERE key='problem_listing_version'") as cursor:
        initialized = bool(await cursor.fetchone())
    for statement in _SCHEMA:
        await db.execute(statement)
    async with db.execute("PRAGMA table_info(problem_listing_native_tags)") as cursor:
        native_columns = {row["name"] for row in await cursor.fetchall()}
    if "position" not in native_columns:
        await db.execute("ALTER TABLE problem_listing_native_tags ADD COLUMN position INTEGER NOT NULL DEFAULT 0")
        await db.execute("INSERT OR IGNORE INTO problem_listing_dirty SELECT platform,problem_id FROM crawler_problems WHERE platform='luogu'")
    for table, owner in (("crawler_problems", None), ("recommendations", None),
                         ("submissions", "user_qq_id"), ("user_problem_state", "owner_qq_id")):
        for event, refs in (("INSERT", ("NEW",)), ("DELETE", ("OLD",)), ("UPDATE", ("OLD", "NEW"))):
            statements = []
            for ref in refs:
                if table != "user_problem_state":
                    statements.append(f"INSERT INTO problem_listing_dirty VALUES({ref}.platform,{ref}.problem_id) ON CONFLICT DO NOTHING;")
                if owner:
                    statements.append(f"INSERT INTO member_problem_dirty VALUES({ref}.{owner},{ref}.platform,{ref}.problem_id) ON CONFLICT DO NOTHING;")
            # Bodies/PDFs and fetch status do not affect the lightweight listing.
            columns = {
                "crawler_problems": "platform,problem_id,contest_id,problem_name,problem_rating,problem_url,tags,metadata_json,created_at",
                "recommendations": "platform,problem_id,problem_name,problem_rating,problem_url,tags",
                "submissions": "user_qq_id,platform,problem_id,problem_name,problem_rating,problem_url,tags,submit_time",
                "user_problem_state": "owner_qq_id,platform,problem_id,is_favorite,state",
            }[table]
            clause = "UPDATE OF " + columns if event == "UPDATE" else event
            await db.execute(f"CREATE TRIGGER IF NOT EXISTS listing_{table}_{event.lower()} AFTER {clause} ON {table} BEGIN "
                             + " ".join(statements) + " END")
    for event, refs in (("INSERT", ("NEW",)), ("DELETE", ("OLD",)), ("UPDATE", ("OLD", "NEW"))):
        statements = ["INSERT INTO problem_listing_dirty SELECT platform,problem_id FROM crawler_problems "
                      f"WHERE platform={ref}.platform AND contest_id={ref}.contest_id ON CONFLICT DO NOTHING;" for ref in refs]
        await db.execute(f"CREATE TRIGGER IF NOT EXISTS listing_contests_{event.lower()} AFTER {event} ON crawler_contests BEGIN "
                         + " ".join(statements) + " END")
    await db.execute("""CREATE TRIGGER IF NOT EXISTS listing_tag_insert AFTER INSERT ON problem_listing_tags BEGIN
        INSERT INTO problem_listing_tag_options VALUES(NEW.platform,NEW.tag_key,NEW.tag,1)
        ON CONFLICT(platform,tag_key) DO UPDATE SET uses=uses+1,tag=MIN(tag,excluded.tag); END""")
    await db.execute("""CREATE TRIGGER IF NOT EXISTS listing_tag_delete AFTER DELETE ON problem_listing_tags BEGIN
        UPDATE problem_listing_tag_options SET uses=uses-1 WHERE platform=OLD.platform AND tag_key=OLD.tag_key;
        DELETE FROM problem_listing_tag_options WHERE platform=OLD.platform AND tag_key=OLD.tag_key AND uses=0;
        UPDATE problem_listing_tag_options SET tag=(SELECT MIN(tag) FROM problem_listing_tags
          WHERE platform=OLD.platform AND tag_key=OLD.tag_key)
          WHERE platform=OLD.platform AND tag_key=OLD.tag_key AND tag=OLD.tag; END""")
    if initialized:
        return
    for table in ("crawler_problems", "recommendations", "submissions"):
        await db.execute(f"INSERT OR IGNORE INTO problem_listing_dirty SELECT platform,problem_id FROM {table}")
    for table, owner in (("submissions", "user_qq_id"), ("user_problem_state", "owner_qq_id")):
        await db.execute(f"INSERT OR IGNORE INTO member_problem_dirty SELECT {owner},platform,problem_id FROM {table}")
    await db.execute("INSERT INTO settings(key,value) VALUES('problem_listing_version','1')")


def _identity_where(platform, key):
    aliases = problem_id_aliases(platform, key)
    column = "problem_id COLLATE NOCASE" if platform in {"codeforces", "luogu"} else "problem_id"
    return column + " IN (" + ",".join("?" for _ in aliases) + ")", aliases


def _tags(value):
    values = problem_tags(value)
    return json.dumps(values, ensure_ascii=False) if values else ""


def _replace_tags(db, table, columns, identity, tags):
    where = " AND ".join(column + "=?" for column in columns)
    db.execute(f"DELETE FROM {table} WHERE {where}", identity)
    rows = [(*identity, tag.casefold(), tag) for tag in problem_tags(tags)]
    if rows:
        db.executemany(f"INSERT INTO {table} VALUES(" + ",".join("?" for _ in rows[0]) + ")", rows)


def _refresh_catalog(db, platform, key, now):
    clause, aliases = _identity_where(platform, key)
    old = db.execute("SELECT * FROM problem_listing WHERE platform=? AND id_key=?", (platform, key)).fetchone()
    catalog = [dict(row) for row in db.execute(
        "SELECT c.problem_id,c.problem_name,c.problem_rating,c.problem_url,c.tags,c.metadata_json,c.updated_at,"
        "CAST(strftime('%s',c.created_at) AS INTEGER) AS first_seen,d.start_time "
        "FROM crawler_problems c LEFT JOIN crawler_contests d ON d.platform=c.platform AND d.contest_id=c.contest_id "
        "WHERE c.platform=? AND c." + clause, (platform, *aliases))]
    recommended = [dict(row) for row in db.execute(
        "SELECT problem_id,problem_name,problem_rating,problem_url,tags FROM recommendations WHERE platform=? AND " + clause,
        (platform, *aliases))]
    fallback = db.execute("SELECT problem_id,problem_name,problem_rating,problem_url FROM submissions WHERE platform=? AND "
                          + clause + " ORDER BY submit_time DESC,problem_id LIMIT 1", (platform, *aliases)).fetchone()
    sources = sorted(recommended, key=lambda row: row["problem_id"]) or sorted(catalog, key=lambda row: row["problem_id"])
    if not sources and fallback:
        sources = [dict(fallback)]
    if not sources:
        db.execute("DELETE FROM problem_listing_tags WHERE platform=? AND id_key=?", (platform, key))
        db.execute("DELETE FROM problem_listing_native_tags WHERE platform=? AND id_key=?", (platform, key))
        db.execute("DELETE FROM problem_listing WHERE platform=? AND id_key=?", (platform, key))
        return old is not None
    source = sources[0]
    tags = next((_tags(row["tags"]) for rows in (catalog, recommended)
                 for row in sorted(rows, key=lambda row: row["problem_id"]) if problem_tags(row["tags"])), "")
    source_time = max((row["start_time"] for row in catalog if platform != "luogu" and row["start_time"] and row["start_time"] > 0), default=None)
    first_seen = min([row["first_seen"] for row in catalog if row["first_seen"] is not None]
                     + ([old["first_seen_at"]] if old else []) or [now])
    numeric = str(source["problem_rating"]) if source["problem_rating"] is not None else ""
    native = {}
    if platform == "luogu" and catalog:
        ordered = sorted(catalog, key=lambda row: row["updated_at"], reverse=True)
        ordered.sort(key=lambda row: 0 if row["problem_id"].startswith("P") else 1 if row["problem_id"].startswith("p") else 2)
        try:
            native = json.loads(ordered[0]["metadata_json"] or "{}").get("luogu", {})
        except (ValueError, TypeError):
            pass
    public = int(platform != "luogu" or bool(re.fullmatch(r"P[1-9][0-9]{0,8}", key)))
    values = (platform, key, key if platform == "luogu" else source["problem_id"], source["problem_name"],
              None if platform == "luogu" else source["problem_rating"], source["problem_url"], tags,
              int(numeric) if re.fullmatch(r"[0-9]{1,6}", numeric) and platform != "luogu" else None,
              source_time, first_seen, int(source_time is None), -(source_time if source_time is not None else first_seen),
              native.get("difficulty"), public)
    native_ids = list(dict.fromkeys(tag for tag in native.get("tag_ids", []) if type(tag) is int))
    old_native = [row[0] for row in db.execute("SELECT tag_id FROM problem_listing_native_tags WHERE platform=? AND id_key=? ORDER BY position,tag_id", (platform, key))] if platform == "luogu" else []
    if old and tuple(old) == values and old_native == native_ids:
        return False
    columns = ("platform", "id_key", "problem_id", "problem_name", "problem_rating", "problem_url", "tags", "rating_number",
               "source_time", "first_seen_at", "sort_unknown", "sort_order", "native_difficulty", "is_public")
    db.execute("INSERT INTO problem_listing VALUES(" + ",".join("?" for _ in values) + ") ON CONFLICT(platform,id_key) DO UPDATE SET "
               + ",".join(name + "=excluded." + name for name in columns[2:]), values)
    if not old or old["tags"] != tags or old["is_public"] != public:
        _replace_tags(db, "problem_listing_tags", ("platform", "id_key"), (platform, key), tags if public else "")
    db.execute("DELETE FROM problem_listing_native_tags WHERE platform=? AND id_key=?", (platform, key))
    db.executemany("INSERT INTO problem_listing_native_tags VALUES(?,?,?,?)", [(platform, key, tag, pos) for pos, tag in enumerate(native_ids)])
    return True


def _refresh_member(db, owner, platform, key):
    old = db.execute("SELECT * FROM member_problem_index WHERE owner=? AND platform=? AND id_key=?", (owner, platform, key)).fetchone()
    clause, aliases = _identity_where(platform, key)
    ac = list(db.execute("SELECT submit_time,tags FROM submissions INDEXED BY idx_submissions_member_identity WHERE user_qq_id=? AND platform=? AND " + clause
                         + " ORDER BY submit_time DESC,problem_id", (owner, platform, *aliases)))
    states = list(db.execute("SELECT is_favorite,state FROM user_problem_state WHERE owner_qq_id=? AND platform=? AND " + clause,
                             (owner, platform, *aliases)))
    if not ac and not states:
        db.execute("DELETE FROM member_problem_index WHERE owner=? AND platform=? AND id_key=?", (owner, platform, key))
        db.execute("DELETE FROM member_problem_tags WHERE owner=? AND platform=? AND id_key=?", (owner, platform, key))
        return old is not None
    own_tags = next((_tags(row["tags"]) for row in ac if problem_tags(row["tags"])), "")
    ac_at = ac[0]["submit_time"] if ac else None
    values = (owner, platform, key, ac_at, -ac_at if ac_at is not None else None, own_tags,
              max((row["is_favorite"] for row in states), default=0), int(any((row["state"] or "inbox") != "inbox" for row in states)))
    if old and tuple(old) == values:
        return False
    db.execute("INSERT INTO member_problem_index VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(owner,platform,id_key) DO UPDATE SET "
               "ac_at=excluded.ac_at,ac_order=excluded.ac_order,own_tags=excluded.own_tags,is_favorite=excluded.is_favorite,"
               "outside_inbox=excluded.outside_inbox", values)
    if not old or old["own_tags"] != own_tags:
        _replace_tags(db, "member_problem_tags", ("owner", "platform", "id_key"), (owner, platform, key), own_tags)
    return True


class ListingConnection(sqlite3.Connection):
    """Use sqlite3's supported factory hook to index writes inside their commit.

    The factory is shared by existing API, sync and job connections. Queue
    triggers contain only built-in SQL so older writers can still write; startup
    initialization drains their durable queue before serving requests.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.row_factory = sqlite3.Row

    def commit(self):
        try:
            if self.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='problem_listing_dirty'").fetchone():
                dirty = {(row[0], problem_id_key(row[0], row[1])) for row in self.execute("SELECT platform,problem_id FROM problem_listing_dirty")}
                members = {(row[0], row[1], problem_id_key(row[1], row[2])) for row in self.execute("SELECT owner,platform,problem_id FROM member_problem_dirty")}
                now = int(time.time())
                public_changed = False
                for platform, key in sorted(dirty):
                    public_changed = _refresh_catalog(self, platform, key, now) or public_changed
                changed_owners = set()
                for owner, platform, key in sorted(members):
                    if _refresh_member(self, owner, platform, key):
                        changed_owners.add(owner)
                if public_changed:
                    self.execute("INSERT INTO settings(key,value) VALUES('problem_listing_revision','1') "
                                 "ON CONFLICT(key) DO UPDATE SET value=CAST(value AS INTEGER)+1")
                for owner in sorted(changed_owners):
                    version_key = "problem_listing_member:" + owner
                    if self.execute("SELECT 1 FROM member_problem_index WHERE owner=? LIMIT 1", (owner,)).fetchone():
                        # Opaque revisions cannot collide after removing/recreating all personal state.
                        self.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                     (version_key, secrets.token_hex(16)))
                    else:
                        self.execute("DELETE FROM settings WHERE key=?", (version_key,))
                self.execute("DELETE FROM problem_listing_dirty")
                self.execute("DELETE FROM member_problem_dirty")
            super().commit()
        except BaseException:
            super().rollback()
            raise


async def indexed_query(db, owner, args):
    """Build one filter shared by count/page; enrich personal data after paging."""
    platform = args.get("platform", "")
    scope = args.get("scope", "all")
    if scope not in {"all", "solved"}:
        raise ValueError("无效的题目范围。")
    state = args.get("state", "")
    source, params = "problem_listing p", []
    if scope == "solved" or state == "favorite":
        # Keep COUNT on the same member range as the page, even without ORDER BY.
        source = "member_problem_index m CROSS JOIN problem_listing p ON m.platform=p.platform AND m.id_key=p.id_key AND m.owner=?"
        params.append(owner)
    conditions = ["p.is_public=1"]
    if scope == "solved":
        conditions.append("m.ac_at IS NOT NULL")
    if state == "favorite":
        conditions.append("m.is_favorite=1")
    elif state == "inbox":
        conditions.append("NOT EXISTS(SELECT 1 FROM member_problem_index s WHERE s.owner=? AND s.platform=p.platform AND s.id_key=p.id_key AND s.outside_inbox=1)")
        params.append(owner)
    if platform:
        conditions.append("p.platform=?")
        params.append(platform)
    tag = str(args.get("tag", "")).strip()[:100]
    if tag:
        conditions.append("(p.problem_name LIKE ? OR p.problem_id LIKE ? OR p.id_key LIKE ? OR p.tags LIKE ? OR "
                          "(p.platform='codeforces' AND p.id_key=?) OR (p.platform='luogu' AND p.id_key=?) OR "
                          "(p.tags='' AND EXISTS(SELECT 1 FROM member_problem_index s WHERE s.owner=? "
                          "AND s.platform=p.platform AND s.id_key=p.id_key AND s.own_tags LIKE ?)))")
        params.extend([f"%{tag}%"] * 4 + [problem_id_key("codeforces", tag), problem_id_key("luogu", tag), owner, f"%{tag}%"])
    selected = selected_problem_tag_keys(args, platform)
    if selected:
        marks = ",".join("?" for _ in selected)
        # Public tags and the member fallback are mutually exclusive per problem.
        candidates = f"""SELECT platform,id_key FROM problem_listing_tags WHERE tag_key IN ({marks})
            UNION ALL SELECT t.platform,t.id_key FROM member_problem_tags t
            JOIN problem_listing c ON c.platform=t.platform AND c.id_key=t.id_key
            WHERE t.owner=? AND t.tag_key IN ({marks}) AND c.tags=''"""
        tag_params = [*selected, owner, *selected]
        if len(selected) > 1:
            candidates = "SELECT platform,id_key FROM (" + candidates + ") GROUP BY platform,id_key HAVING COUNT(*)=?"
            tag_params.append(len(selected))
        if scope == "all" and state != "favorite":
            # Selective tags start at their indexed references, not the entire OJ.
            source = "(" + candidates + ") selected CROSS JOIN problem_listing p ON p.platform=selected.platform AND p.id_key=selected.id_key"
            params[0:0] = tag_params
        else:
            conditions.append("(p.platform,p.id_key) IN (" + candidates + ")")
            params.extend(tag_params)
    from .luogu_problem import native_filter
    native, native_params = await native_filter(db, args, platform, indexed=True)
    query = "SELECT p.*" + (",m.ac_at,m.ac_order" if scope == "solved" else "") + " FROM " + source + " WHERE " + " AND ".join(conditions) + native
    params.extend(native_params)
    return await _range_query(db, query, params, args, platform, indexed=True)


async def listing_version(db, owner):
    async with db.execute("SELECT key,value FROM settings WHERE key IN (?,?)", ("problem_listing_revision", "problem_listing_member:" + owner)) as cursor:
        versions = dict(await cursor.fetchall())
    return versions.get("problem_listing_revision", "0") + ":" + versions.get("problem_listing_member:" + owner, "0")


async def listing_tags(db, owner, platform):
    query = """SELECT tag_key,MIN(tag) AS tag FROM (
        SELECT platform,tag_key,tag FROM problem_listing_tag_options
        UNION ALL SELECT t.platform,t.tag_key,t.tag FROM member_problem_tags t
        JOIN problem_listing p ON p.platform=t.platform AND p.id_key=t.id_key
        WHERE t.owner=? AND p.tags='' AND p.is_public=1) WHERE 1=1"""
    params = [owner]
    if platform:
        query += " AND platform=?"
        params.append(platform)
    async with db.execute(query + " GROUP BY tag_key ORDER BY tag_key", params) as cursor:
        return [row["tag"] for row in await cursor.fetchall() if len(row["tag"]) <= 100]


async def listing_query(db, base, params, args, platform):
    """Compatibility for raw catalog/admin callers, using persisted time data."""
    await db.create_function("problem_id_key", 2, problem_id_key, deterministic=True)
    query = """SELECT p.*,t.source_time,t.first_seen_at,
        COALESCE(t.source_time,t.first_seen_at) AS problem_time,
        CASE WHEN t.source_time IS NOT NULL THEN 'contest'
             WHEN t.first_seen_at IS NOT NULL THEN 'first_seen' ELSE 'unknown' END AS time_basis,
        COALESCE(t.sort_unknown,1) AS sort_unknown,COALESCE(t.sort_order,0) AS sort_order
        FROM (""" + base + """) p LEFT JOIN problem_listing t
        ON t.platform=p.platform AND t.id_key=problem_id_key(p.platform,p.problem_id)
        WHERE COALESCE(t.is_public,1)=1"""
    return await _range_query(db, query, params, args, platform)


async def _range_query(db, query, params, args, platform, *, indexed=False):
    def numeric_rating(value):
        text = str(value) if value is not None else ""
        return int(text) if re.fullmatch(r"[0-9]{1,6}", text) else None
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
        if not indexed:
            await db.create_function("problem_rating_number", 1, numeric_rating, deterministic=True)
        column = "p.rating_number" if indexed else "problem_rating_number(p.problem_rating)"
        query += " AND " + column + " IS NOT NULL"
        for key, operator in (("rating_min", ">="), ("rating_max", "<=")):
            if key in bounds:
                query += " AND " + column + operator + "?"
                values.append(bounds[key])
    times = time_options(args, platform)
    if times:
        prefix = "p." if indexed else "t."
        if times["time_basis"] == "unknown":
            query += " AND " + prefix + "source_time IS NULL"
        else:
            column = {"contest": prefix + "source_time", "first_seen": prefix + "first_seen_at",
                      "auto": "COALESCE(" + prefix + "source_time," + prefix + "first_seen_at)"}[times["time_basis"]]
            for key, operator in (("start_at", ">="), ("end_at", "<")):
                if key in times:
                    query += " AND " + column + operator + "?"
                    values.append(times[key])
    return query, values


NEWEST_ORDER = " ORDER BY sort_unknown,sort_order,p.platform,problem_id_key(p.platform,p.problem_id),p.problem_id"


async def listing_page(db, owner, args):
    """Count filtered keys, read one indexed page, then enrich only those keys."""
    import base64
    import hashlib
    try:
        scope = args.get("scope", "all")
        page = max(1, int(args.get("page", 1)))
        size = max(1, min(100 if scope == "solved" else 500, int(args.get("page_size", 20 if scope == "solved" else 500))))
    except (TypeError, ValueError):
        raise ValueError("分页参数必须为整数。") from None
    query, params = await indexed_query(db, owner, args)
    async with db.execute("SELECT COUNT(*) FROM (" + query + ")", params) as cursor:
        total = (await cursor.fetchone())[0]
    fingerprint = hashlib.sha256(json.dumps([owner, size, sorted((k, v) for k, v in args.items() if k not in {"page", "cursor", "page_size"})], ensure_ascii=False).encode()).hexdigest()[:24]
    order = "m.ac_order,m.platform,m.id_key" if scope == "solved" else "p.sort_unknown,p.sort_order,p.platform,p.id_key"
    page_params = list(params)
    raw_cursor = args.get("cursor")
    if raw_cursor:
        try:
            if len(raw_cursor) > 2048:
                raise ValueError()
            payload = json.loads(base64.b64decode(raw_cursor + "=" * (-len(raw_cursor) % 4), altchars=b"-_", validate=True))
            keys = payload["keys"]
            if payload["query"] != fingerprint or payload["page"] != page or len(keys) != (3 if scope == "solved" else 4):
                raise ValueError()
            numeric = 1 if scope == "solved" else 2
            if any(type(value) is not int or not -(2**63) <= value < 2**63 for value in keys[:numeric]) or any(not isinstance(value, str) for value in keys[numeric:]):
                raise ValueError()
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise ValueError("分页游标无效或与当前筛选条件不一致，请重新加载。") from None
        query += " AND (" + order + ")>(" + ",".join("?" for _ in keys) + ")"
        page_params.extend(keys)
    query += " ORDER BY " + order + " LIMIT ?"
    page_params.append(size)
    if not raw_cursor:
        query += " OFFSET ?"
        page_params.append((page - 1) * size)
    async with db.execute(query, page_params) as cursor:
        records = [dict(row) for row in await cursor.fetchall()]
    states = {}
    if records:
        marks = ",".join("(?,?)" for _ in records)
        keys = [value for row in records for value in (row["platform"], row["id_key"])]
        async with db.execute("WITH page(platform,id_key) AS (VALUES " + marks + ") "
                              "SELECT s.* FROM page JOIN member_problem_index s "
                              "ON s.owner=? AND s.platform=page.platform AND s.id_key=page.id_key", [*keys, owner]) as cursor:
            states = {(row["platform"], row["id_key"]): dict(row) for row in await cursor.fetchall()}
    items = []
    for row in records:
        item = {name: row[name] for name in ("platform", "problem_id", "problem_name", "problem_rating", "problem_url", "tags", "source_time", "first_seen_at")}
        state = states.get((row["platform"], row["id_key"]), {})
        item["tags"] = item["tags"] or state.get("own_tags", "")
        item["is_favorite"] = state.get("is_favorite", 0)
        item["problem_time"] = row["source_time"] if row["source_time"] is not None else row["first_seen_at"]
        item["time_basis"] = "contest" if row["source_time"] is not None else "first_seen"
        if scope == "solved":
            item["ac_at"] = row["ac_at"]
        items.append(item)
    next_cursor = None
    if records and page * size < total:
        last = records[-1]
        keys = ([last["ac_order"], last["platform"], last["id_key"]] if scope == "solved" else
                [last["sort_unknown"], last["sort_order"], last["platform"], last["id_key"]])
        next_cursor = base64.urlsafe_b64encode(json.dumps({"query": fingerprint, "page": page + 1, "keys": keys}, separators=(",", ":")).encode()).decode().rstrip("=")
    return {"items": items, "total": total, "returned": len(items), "page": page, "page_size": size, "next_cursor": next_cursor, "tags_version": await listing_version(db, owner)}
