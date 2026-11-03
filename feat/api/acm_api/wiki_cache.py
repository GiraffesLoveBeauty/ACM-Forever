"""Application-owned, bounded cache of completed public Wiki JSON responses."""

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import time


@dataclass(frozen=True)
class CachedResponse:
    body: bytes
    content_type: str
    etag: str
    created_at: float


class WikiResponseCache:
    def __init__(
        self,
        max_entries=256,
        max_bytes=8 * 1024 * 1024,
        max_entry_bytes=256 * 1024,
        ttl=300,
        clock=time.monotonic,
    ):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.max_entry_bytes = max_entry_bytes
        self.ttl = ttl
        self.clock = clock
        self.entries = OrderedDict()
        self.bytes = 0
        self.hits = self.misses = self.evictions = 0
        self.generation = 0

    def _remove(self, key):
        self.bytes -= len(self.entries.pop(key).body)

    def get(self, key):
        entry = self.entries.get(key)
        if entry is not None and self.clock() - entry.created_at >= self.ttl:
            self._remove(key)
            entry = None
        if entry is None:
            self.misses += 1
            return None
        self.entries.move_to_end(key)
        self.hits += 1
        return entry

    def put(self, key, body, content_type, etag):
        size = len(body)
        if (
            not self.max_entries
            or self.ttl <= 0
            or size > min(self.max_entry_bytes, self.max_bytes)
        ):
            return False
        now = self.clock()
        for old, entry in list(self.entries.items()):
            if now - entry.created_at >= self.ttl:
                self._remove(old)
        if key in self.entries:
            self._remove(key)
        while self.entries and (
            len(self.entries) >= self.max_entries
            or self.bytes + size > self.max_bytes
        ):
            self._remove(next(iter(self.entries)))
            self.evictions += 1
        self.entries[key] = CachedResponse(body, content_type, etag, now)
        self.bytes += size
        return True

    def clear(self):
        self.entries.clear()
        self.bytes = 0
        self.generation += 1

    def stats(self):
        return {
            "entries": len(self.entries),
            "bytes": self.bytes,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
        }


def database_namespace(path):
    """Separate live database files; an in-place restore still requires cache reset."""
    path = Path(path).resolve()
    stat = path.stat()
    return str(path), stat.st_dev, stat.st_ino
