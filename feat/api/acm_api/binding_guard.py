"""Guard non-CF crawler batches against changes to their captured binding generation."""
from .binding_service import platform_spec, row
from .account_lifecycle_service import AccountLifecycleError, snapshot_epoch


class BindingChanged(RuntimeError):
    pass


class BindingGuard:
    def __init__(self, connection, user, platform):
        try:
            self.epoch = snapshot_epoch(user)
        except AccountLifecycleError as error:
            raise BindingChanged(str(error)) from None
        self.connection = connection
        self.platform, self.field, self.version_field = platform_spec(platform)
        self.qq_id = str(user["qq_id"])
        self.account = str(user[self.field] or "").strip().casefold()
        self.version = int(user[self.version_field]) if self.version_field in user.keys() else 0

    def __getattr__(self, key):
        return getattr(self.connection, key)

    async def check(self):
        current = await row(self.connection, f"SELECT {self.field} AS account,{self.version_field} AS version FROM users WHERE account_state='active' AND account_epoch=? AND qq_id=?", (self.epoch, self.qq_id,))
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