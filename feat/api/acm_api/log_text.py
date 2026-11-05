"""Terminal-safe, single-line log text shared by producer and viewer."""
import unicodedata


def clean(value, limit=240):
    text = "".join(" " if unicodedata.category(c).startswith("C") else c for c in str(value))
    return " ".join(text.split())[:limit]
