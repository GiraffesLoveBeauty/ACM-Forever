"""Effective labels are a read-only view over automatic results and a manual journal."""
from .service import TagManager, get_effective_tags, get_effective_tags_many, iter_effective_tags

__all__ = ["TagManager", "get_effective_tags", "get_effective_tags_many", "iter_effective_tags"]
