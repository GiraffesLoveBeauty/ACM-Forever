"""Switches for user AC synchronization, separate from catalog collection."""

SYNC_PAUSED = -5


def submission_sync_paused(platform, config):
    return platform == "luogu" and config.get("luogu_user_sync_enabled", True) is not True


class SyncFailure(int):
    """Preserve the numeric sync contract while carrying an actionable failure."""

    def __new__(cls, message, *, code="fetch_failed", retry_after=0):
        value = super().__new__(cls, -1)
        value.message = str(message)[:500]
        value.code = code
        value.retry_after = max(0, int(retry_after))
        return value
