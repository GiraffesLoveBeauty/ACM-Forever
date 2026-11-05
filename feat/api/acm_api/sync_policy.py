"""Temporary switches for user submission synchronization, separate from catalogs."""

SYNC_PAUSED = -5


def submission_sync_paused(platform, config):
    # Credentials alone must not resume Luogu traffic during the pause.
    return platform == "luogu" and config.get("luogu_user_sync_enabled") is not True
