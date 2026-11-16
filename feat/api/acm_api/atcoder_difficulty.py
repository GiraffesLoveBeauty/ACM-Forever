"""AtCoder Problems estimated difficulty; independent from contest points/CF."""
import json
import math

MODELS_URL = "https://kenkoooo.com/atcoder/resources/problem-models.json"


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
