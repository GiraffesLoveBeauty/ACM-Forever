# -*- coding: utf-8 -*-
"""Pure helpers for explainable training recommendations and tag mastery."""
import math
import re


def split_tags(value):
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        raw = value
    else:
        raw = re.split(r"[,|;，；]", str(value))
    result, seen = [], set()
    for item in raw:
        tag = str(item or "").strip()
        key = tag.casefold()
        if tag and key not in seen:
            seen.add(key)
            result.append(tag)
    return result


def numeric_rating(value):
    try:
        rating = int(float(value))
        return rating if rating > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def score_candidate(candidate, target_rating, weak_tags=(), due_tags=()):
    """Return 0..100 score, stable explanation and component breakdown."""
    rating = numeric_rating(candidate.get("problem_rating"))
    target = numeric_rating(target_rating)
    tags = split_tags(candidate.get("tags"))
    weak = {str(tag).casefold() for tag in weak_tags}
    due = {str(tag).casefold() for tag in due_tags}
    matched_weak = [tag for tag in tags if tag.casefold() in weak]
    matched_due = [tag for tag in tags if tag.casefold() in due]
    if rating is not None and target is not None:
        difficulty = max(0.0, 1.0 - abs(rating - target) / 400.0)
        reason = f"难度 {rating} 接近目标 {target}"
    else:
        difficulty = 0.35
        reason = "题目难度资料不足，按其他训练信号推荐"
    weak_score = 1.0 if matched_weak else 0.0
    due_score = 1.0 if matched_due else 0.0
    novelty = 0.0 if candidate.get("recently_challenged") else 1.0
    score = round(100 * (0.55 * difficulty + 0.25 * weak_score + 0.15 * due_score + 0.05 * novelty), 1)
    reasons = [reason]
    if matched_weak:
        reasons.append("匹配薄弱标签：" + ", ".join(matched_weak[:3]))
    if matched_due:
        reasons.append("包含到期复习标签：" + ", ".join(matched_due[:3]))
    if candidate.get("recently_challenged"):
        reasons.append("近期挑战过，降低重复推荐优先级")
    return {"score": score, "reason": "；".join(reasons), "tags": tags,
            "breakdown": {"difficulty": round(difficulty, 3), "weak_tag": weak_score,
                          "due_review": due_score, "novelty": novelty}}


def tag_mastery(rows):
    """Aggregate per-tag mastery from solved problems and their observed attempts."""
    stats = {}
    for row in rows:
        tags = split_tags(row.get("tags"))
        if not tags:
            continue
        attempts = max(1, int(row.get("attempts") or 1))
        solved_at = int(row.get("last_submit") or 0)
        for tag in tags:
            key = tag.casefold()
            item = stats.setdefault(key, {"tag": tag, "solved": 0, "attempts": 0, "mistakes": 0, "last_seen": 0})
            item["solved"] += 1
            item["attempts"] += attempts
            item["mistakes"] += max(0, attempts - 1)
            item["last_seen"] = max(item["last_seen"], solved_at)
    result = []
    for item in stats.values():
        # Bayesian-smoothed success proxy: reward volume, penalize repeated attempts.
        volume = 1.0 - math.exp(-item["solved"] / 5.0)
        quality = item["solved"] / max(item["attempts"], 1)
        mastery = max(0.0, min(1.0, 0.65 * volume + 0.35 * quality))
        result.append({**item, "mastery": round(mastery, 3)})
    return sorted(result, key=lambda item: (item["mastery"], -item["mistakes"], item["tag"].casefold()))
