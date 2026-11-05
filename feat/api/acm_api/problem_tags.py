"""Read catalog tags consistently from legacy text and crawler JSON arrays."""

import json

from .training_logic import split_tags


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
