"""Switches for user AC synchronization, separate from catalog collection."""

SYNC_PAUSED = -5


def submission_sync_paused(platform, config):
    return platform == "luogu" and config.get("luogu_user_sync_enabled", True) is not True


def luogu_retry_delay(failures):
    """成员真实失败沿用 1/2/4/8/15 分钟上限；全站受限等待可更长。"""
    return min(900, 60 * 2 ** min(4, max(0, int(failures) - 1)))


class SyncFailure(int):
    """Preserve the numeric sync contract while carrying an actionable failure."""

    def __new__(cls, message, *, code="fetch_failed", retry_after=0, http_status=None,
                cause_http_status=None, deferred=False, consecutive_failures=0, attention_required=False):
        value = super().__new__(cls, -1)
        value.message = str(message)[:500]
        value.code = code
        value.retry_after = max(0, int(retry_after))
        # None 表示本次没有收到 HTTP 响应；冷却来源单列，不能伪造本次状态码。
        value.http_status = http_status
        value.cause_http_status = cause_http_status
        value.deferred = bool(deferred)
        value.consecutive_failures = int(consecutive_failures)
        value.attention_required = bool(attention_required)
        return value
