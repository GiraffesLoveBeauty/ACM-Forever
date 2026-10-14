"""Common helpers for local JSON sampling tools."""

import argparse
import json


def positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("必须为正整数")
    return number


def json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    return "object"


def field_report(records):
    records = list(records)
    fields = {}
    for record in records:
        for key, value in record.items():
            entry = fields.setdefault(key, {"present": 0, "types": set()})
            entry["present"] += 1
            entry["types"].add(json_type(value))
    return {
        key: {
            "present": entry["present"],
            "missing": len(records) - entry["present"],
            "types": sorted(entry["types"]),
        }
        for key, entry in sorted(fields.items())
    }


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
