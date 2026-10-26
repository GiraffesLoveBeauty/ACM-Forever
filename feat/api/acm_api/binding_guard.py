"""Guard non-CF crawler batches against changes to their captured binding generation."""
from .binding_service import platform_spec, row


class BindingChanged(RuntimeError):
    pass


class BindingGuard:
    def __init__(self, connection, user, platform):
        self.connection = connection
        self.platform, self.field, self.version_field = platform_spec(platform)
        self.qq_id = str(user["qq_id"])
        self.account = str(user[self.field] or "").strip().casefold()
        self.version = int(user[self.version_field]) if self.version_field in user.keys() else 0

    def __getattr__(self, key):
        return getattr(self.connection, key)

    async def check(self):
        current = await row(self.connection, f"SELECT {self.field} AS account,{self.version_field} AS version FROM users WHERE qq_id=?", (self.qq_id,))
        if not current or str(current["account"] or "").strip().casefold() != self.account or int(current["version"]) != self.version:
            raise BindingChanged("绑定已变化，旧账号同步结果已丢弃")

    async def executemany(self, sql, parameters):
        # Crawlers only write through executemany; reads retain aiosqlite's cursor API.
        # Acquire the write lock after network IO and before checking the generation.
        if not self.connection.in_transaction:
            await self.connection.execute("BEGIN IMMEDIATE")
        try:
            await self.check()
            return await self.connection.executemany(sql, parameters)
        except BaseException:
            await self.connection.rollback()
            raise