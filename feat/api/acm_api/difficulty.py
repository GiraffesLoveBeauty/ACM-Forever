# -*- coding: utf-8 -*-
"""平台难度定义、校验与今日训练筛选条件。"""

LUOGU_DIFFICULTIES = (
    "未评定",
    "入门",
    "普及-",
    "普及/提高-",
    "普及+/提高",
    "提高+/省选-",
    "省选/NOI-",
    "NOI/NOI+/CTSC",
)

NOWCODER_DIFFICULTIES = ("1星", "2星", "3星", "4星", "5星")

PLATFORM_ALIASES = {
    "cf": "codeforces",
    "codeforces": "codeforces",
    "洛谷": "luogu",
    "luogu": "luogu",
    "at": "atcoder",
    "atc": "atcoder",
    "atcoder": "atcoder",
    "牛客": "nowcoder",
    "nowcoder": "nowcoder",
}


def normalize_platform(value):
    key = str(value or "").strip().lower()
    return PLATFORM_ALIASES.get(key, key)


def normalize_problem_difficulty(platform, value):
    """将爬虫/API 返回值规范化为数据库和界面使用的文本。"""
    platform = normalize_platform(platform)
    text = str(value or "").strip()
    if not text:
        return ""
    if platform in {"codeforces", "atcoder"}:
        try:
            return str(int(round(float(text))))
        except (TypeError, ValueError):
            return ""
    if platform == "luogu":
        return text if text in LUOGU_DIFFICULTIES else ""
    if platform == "nowcoder":
        if text in NOWCODER_DIFFICULTIES:
            return text
        digits = "".join(char for char in text if char.isdigit())
        if digits and f"{digits[0]}星" in NOWCODER_DIFFICULTIES:
            return f"{digits[0]}星"
    return ""


def challenge_filter(platform, difficulty, column="r.problem_rating"):
    """返回今日训练使用的 SQL 条件、参数和规范化显示值。

    选择全部平台时不应用难度条件。数字平台以目标值 ±100 匹配，
    标签平台使用精确匹配。
    """
    platform = normalize_platform(platform)
    if not platform:
        return "", [], "不限"
    if platform == "codeforces":
        try:
            target = int(difficulty)
        except (TypeError, ValueError):
            raise ValueError("Codeforces 难度必须是 800-3500 的整数 Rating。")
        if not 800 <= target <= 3500:
            raise ValueError("Codeforces 难度必须是 800-3500 的整数 Rating。")
        return f"NULLIF(TRIM({column}), '') IS NOT NULL AND CAST({column} AS INTEGER) BETWEEN ? AND ?", [target - 100, target + 100], str(target)
    if platform == "atcoder":
        try:
            target = int(difficulty)
        except (TypeError, ValueError):
            raise ValueError("AtCoder 难度必须是 0-4000 的整数。")
        if not 0 <= target <= 4000:
            raise ValueError("AtCoder 难度必须是 0-4000 的整数。")
        return f"NULLIF(TRIM({column}), '') IS NOT NULL AND CAST({column} AS INTEGER) BETWEEN ? AND ?", [max(0, target - 100), target + 100], str(target)
    if platform == "luogu":
        value = normalize_problem_difficulty(platform, difficulty)
        if not value:
            raise ValueError("请选择有效的洛谷难度标签。")
        return f"{column} = ?", [value], value
    if platform == "nowcoder":
        value = normalize_problem_difficulty(platform, difficulty)
        if not value:
            raise ValueError("请选择有效的牛客难度星级。")
        return f"{column} = ?", [value], value
    raise ValueError("暂不支持该平台的今日训练难度筛选。")


def challenge_time_limit(platform, difficulty):
    """按平台难度估算单题训练时限（分钟）。"""
    platform = normalize_platform(platform)
    if platform == "codeforces":
        target = int(difficulty)
        return max(10, min(90, 75 - max(0, target - 800) // 40))
    if platform == "atcoder":
        target = int(difficulty)
        return max(10, min(90, 75 - max(0, target - 400) // 40))
    if platform == "luogu":
        value = normalize_problem_difficulty(platform, difficulty)
        return min(90, 25 + LUOGU_DIFFICULTIES.index(value) * 10) if value in LUOGU_DIFFICULTIES else 60
    if platform == "nowcoder":
        value = normalize_problem_difficulty(platform, difficulty)
        return 30 + NOWCODER_DIFFICULTIES.index(value) * 15 if value in NOWCODER_DIFFICULTIES else 60
    return 60


def neighboring_difficulties(platform, difficulty):
    """返回巩固、主训练、挑战三区对应的平台难度。"""
    platform = normalize_platform(platform)
    if not platform:
        return [None, None, None]
    if platform in {"codeforces", "atcoder"}:
        base = int(difficulty)
        minimum, maximum = (800, 3500) if platform == "codeforces" else (0, 4000)
        return [max(minimum, base - 150), max(minimum, min(maximum, base)), min(maximum, base + 150)]
    levels = LUOGU_DIFFICULTIES if platform == "luogu" else NOWCODER_DIFFICULTIES
    value = normalize_problem_difficulty(platform, difficulty)
    if value not in levels:
        raise ValueError("无效的平台难度。")
    index = levels.index(value)
    return [levels[max(0, index - 1)], value, levels[min(len(levels) - 1, index + 1)]]
