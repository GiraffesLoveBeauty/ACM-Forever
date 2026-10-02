"""API-only helpers retained from the NCatBot WebUI backend."""
import re


def valid_contest_report_time(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(value or "").strip()))
