"""Explicit source/first-seen time contracts shared by collection and lists."""
from datetime import datetime, timezone
import re


def timestamp(value, name):
    if type(value) is bool:
        raise ValueError(name + " 必须为 Unix 秒或带时区的 ISO 时间")
    try:
        if type(value) is int or isinstance(value, str) and re.fullmatch(r"[0-9]{1,12}", value):
            result = int(value)
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("时间必须包含时区")
            result = int(parsed.timestamp())
        else:
            raise ValueError("时间格式无效")
        if not 0 <= result <= 253402300799:
            raise ValueError("时间超出范围")
        return result
    except (ValueError, OverflowError, OSError) as error:
        raise ValueError(name + " 必须为有效 Unix 秒或带时区的 ISO 时间") from error


def time_options(data, platform, *, collection=False):
    keys = {key for key in ("start_at", "end_at") if data.get(key) not in (None, "")}
    basis = data.get("time_basis")
    if basis == "unknown" and not collection:
        if keys:
            raise ValueError("未知发布时间筛选不能同时指定时间边界")
        return {"time_basis": "unknown"}
    if not keys:
        if basis not in (None, "", "auto"):
            raise ValueError("选择时间依据时至少提供一个时间边界")
        return {}
    if collection and data.get("scope", "platform") != "platform":
        raise ValueError("时间范围仅用于全平台采集")
    basis = basis or ("first_seen" if platform == "luogu" else "contest")
    if basis not in {"contest", "first_seen", "auto"} or platform == "luogu" and basis == "contest":
        raise ValueError("无效时间依据；洛谷仅支持本站首次收录时间")
    if collection and basis == "auto":
        raise ValueError("采集时间范围须明确选择比赛时间或首次收录时间")
    result = {key: timestamp(data[key], key) for key in keys}
    if "start_at" in result and "end_at" in result and result["start_at"] >= result["end_at"]:
        raise ValueError("结束时间必须晚于开始时间，范围为左闭右开")
    result["time_basis"] = basis
    return result


async def filter_collection_time(db, platform, items, options, result):
    if not any(key in options for key in ("start_at", "end_at")):
        return items
    async with db.execute("SELECT problem_id,CAST(strftime('%s',created_at) AS INTEGER) FROM crawler_problems WHERE platform=?", (platform,)) as cursor:
        first_seen = dict(await cursor.fetchall())
    async with db.execute("SELECT contest_id,start_time FROM crawler_contests WHERE platform=?", (platform,)) as cursor:
        starts = dict(await cursor.fetchall())
    now = int(datetime.now(timezone.utc).timestamp())
    selected, unknown = [], 0
    for item in items:
        value = (first_seen.get(item["problem_id"], now) if options["time_basis"] == "first_seen"
                 else starts.get(item.get("contest_id")))
        if value is None or options["time_basis"] == "contest" and value <= 0:
            unknown += 1
            continue
        if options.get("start_at", 0) <= value < options.get("end_at", 253402300800):
            selected.append(item)
    result.update(time_basis=options["time_basis"], time_unknown_count=unknown,
                  time_filtered_count=len(items) - len(selected) - unknown)
    return selected
