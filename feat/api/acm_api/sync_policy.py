"""Switches for user AC synchronization, separate from catalog collection."""

SYNC_PAUSED = -5


def submission_sync_paused(platform, config):
    return platform == "luogu" and config.get("luogu_user_sync_enabled", True) is not True
