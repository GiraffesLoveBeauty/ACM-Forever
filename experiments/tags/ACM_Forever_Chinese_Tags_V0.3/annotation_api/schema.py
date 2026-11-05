"""Closed Structured Outputs schema plus stricter application validation."""
import json
from jsonschema import Draft202012Validator
from label_pipeline import TAG_BY_ID, MAPPING, validate_id_list


def object_schema(properties):
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def id_array(kind):
    return {"type": "array", "items": {"type": "string", "enum": [k for k, t in TAG_BY_ID.items() if t["tag_kind"] == kind]}}


SCHEMA = object_schema({
    "problem_key": {"type": "string"}, "content_hash": {"type": "string"},
    "specific_tag_ids": id_array("specific"), "provisional_tag_ids": id_array("provisional"),
    "resolved_cf_hints": {"type": "array", "items": object_schema({
        "hint": {"type": "string", "enum": list(MAPPING["clue"])},
        "specific_tag_ids": id_array("specific")})},
    "evidence_kind": {"type": "string", "enum": ["statement_only", "official_editorial", "other_verified_solution"]},
    "reason": {"type": "string"},
})
VALIDATOR = Draft202012Validator(SCHEMA)


def validate(text, item):
    def pairs(values):
        out = {}
        for k, v in values:
            if k in out:
                raise ValueError("Duplicate JSON property")
            out[k] = v
        return out

    value = json.loads(text, object_pairs_hook=pairs)
    if next(VALIDATOR.iter_errors(value), None) is not None:
        raise ValueError("Response does not conform to annotation schema")
    base = item["rule_base"]
    if value["problem_key"] != base["problem_key"] or value["content_hash"] != base["content_hash"]:
        raise ValueError("Response identity/hash mismatch")
    if not value["reason"].strip():
        raise ValueError("A nonempty review reason is required")
    kind = value["evidence_kind"]
    evidence = item["evidence"]
    if kind != "statement_only" and (not evidence["verified_editorial_markdown"] or kind != evidence["editorial_evidence_kind"]):
        raise ValueError("Response claims unavailable verified evidence")
    resolved = {}
    for entry in value["resolved_cf_hints"]:
        hint = entry["hint"]
        if base["platform"] != "codeforces" or hint not in base["cf_unresolved_hints"] or hint in resolved or not entry["specific_tag_ids"]:
            raise ValueError("Invalid or duplicate CF resolution")
        resolved[hint] = validate_id_list(entry["specific_tag_ids"], "specific", "resolution")
    value["resolved_cf_hints"] = resolved
    for kind, field in (("specific", "specific_tag_ids"), ("provisional", "provisional_tag_ids")):
        value[field] = validate_id_list(value[field], kind, field)
    return value
