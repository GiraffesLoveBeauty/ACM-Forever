"""AtCoder Problems estimated difficulty; independent from contest points/CF."""
import json
import math

MODELS_URL = "https://kenkoooo.com/atcoder/resources/problem-models.json"


def difficulty_metadata(raw):
    """Expose confirmed model provenance, without publishing the stored metadata blob."""
    try:
        metadata = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {}
    if not isinstance(metadata, dict) or metadata.get("difficulty_source") != "atcoder_problems":
        return {}
    value = metadata.get("difficulty_raw")
    experimental = metadata.get("difficulty_is_experimental")
    try:
        valid_raw = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid_raw = False
    return {"difficulty_source": "atcoder_problems",
            "difficulty_raw": value if valid_raw else None,
            "difficulty_is_experimental": experimental if type(experimental) is bool else None}


async def attach_difficulty_metadata(db, items):
    """Enrich paged rows only when their displayed score matches the known local model."""
    wanted = {item["problem_id"] for item in items if item.get("platform") == "atcoder"}
    if not wanted:
        return
    catalog = {}
    ids = sorted(wanted)
    for start in range(0, len(ids), 400):
        batch = ids[start:start + 400]
        async with db.execute(
            "SELECT problem_id,problem_rating,metadata_json FROM crawler_problems "
            "WHERE platform='atcoder' AND problem_id IN (" + ",".join("?" for _ in batch) + ")",
            batch,
        ) as cursor:
            catalog.update((row["problem_id"], dict(row)) for row in await cursor.fetchall())
    for item in items:
        if item.get("platform") != "atcoder":
            continue
        saved = catalog.get(item["problem_id"])
        if saved is None:
            continue
        if type(item.get("problem_rating")) not in (str, int, float):
            continue
        try:
            displayed, stored = float(item["problem_rating"]), float(saved["problem_rating"])
        except (TypeError, ValueError, KeyError, OverflowError):
            continue
        if math.isfinite(displayed) and displayed >= 0 and displayed == stored:
            item.update(difficulty_metadata(saved["metadata_json"]))


def apply_models(items, raw):
    models = json.loads(raw.decode("utf-8-sig") if isinstance(raw, bytes) else raw)
    if not isinstance(models, dict) or any(not isinstance(model, dict) for model in models.values()):
        raise ValueError("AtCoder 难度模型须为以题号为键的对象")
    for item in items:
        model = models.get(item["problem_id"], {})
        raw_value = model.get("difficulty")
        valid = type(raw_value) in (int, float) and math.isfinite(raw_value)
        item["difficulty_raw"] = raw_value if valid else None
        item["difficulty_source"] = "atcoder_problems"
        item["difficulty_missing"] = not valid
        item["difficulty_is_experimental"] = model.get("is_experimental") if type(model.get("is_experimental")) is bool else None
        value = 400 * math.exp(raw_value / 400 - 1) if valid and raw_value < 400 else raw_value
        item["problem_rating"] = max(0, math.floor(value + 0.5)) if valid else None
    return items
