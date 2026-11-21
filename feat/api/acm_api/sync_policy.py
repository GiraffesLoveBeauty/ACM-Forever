"""Switches for user AC synchronization, separate from catalog collection."""


SYNC_PAUSED = -5
# The Luogu account itself has opted out of public practice-page access.  This
# is deliberately distinct from ``SYNC_PAUSED`` (the global deployment switch)
# so one restricted account does not make the whole Luogu worker look paused.
SYNC_LUOGU_ACCESS_RESTRICTED = -6


class SyncOutcome(int):
    """An integer sync result with optional upstream failure metadata.

    Existing callers treat fetcher results as integers.  Keeping the outcome
    as an ``int`` preserves that contract while allowing the sync engine to
    distinguish a Luogu HTTP 403 from an ordinary fetch failure.
    """

    def __new__(cls, value, *, status=None, error_code=None, message=None):
        instance = int.__new__(cls, value)
        instance.status = status
        instance.error_code = error_code
        instance.message = message
        return instance


def sync_result_is_non_failure(value):
    """Return whether a negative result represents an intentional skip."""

    return value in {SYNC_PAUSED, SYNC_LUOGU_ACCESS_RESTRICTED}


def submission_sync_paused(platform, config):
    return platform == "luogu" and config.get("luogu_user_sync_enabled", True) is not True
