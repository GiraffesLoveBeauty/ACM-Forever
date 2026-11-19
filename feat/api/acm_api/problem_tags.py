"""Read catalog tags consistently from legacy text and crawler JSON arrays."""

import json

from .training_logic import split_tags


def selected_problem_tag_keys(args, platform):
    """Read Codeforces intersections and keep legacy exact single-tag links."""
    multiple = args.get("problem_tags", "").strip()
    if multiple:
        if platform != "codeforces":
            raise ValueError("多标签筛选须指定 platform=codeforces。")
        values = [value.strip() for value in multiple.split(",")]
        if not all(values):
            raise ValueError("题目标签不能为空。")
    else:
        single = args.get("problem_tag", "").strip()
        values = [single] if single else []
    if any(len(value) > 100 for value in values):
        raise ValueError("题目标签最多 100 个字符。")
    keys = tuple(dict.fromkeys(value.casefold() for value in values))
    if len(keys) > 20:
        raise ValueError("最多选择 20 个题目标签。")
    return keys


def problem_tags(value):
    if isinstance(value, str) and value.lstrip().startswith("["):
        try:
            decoded = json.loads(value)
        except (ValueError, TypeError):
            pass
        else:
            if isinstance(decoded, list):
                value = [item for item in decoded if isinstance(item, str)]
    return split_tags(value)


def has_problem_tag(value, selected):
    wanted = selected.strip().casefold()
    return int(any(tag.casefold() == wanted for tag in problem_tags(value)))
