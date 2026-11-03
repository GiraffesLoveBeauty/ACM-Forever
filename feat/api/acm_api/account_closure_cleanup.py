"""Leased, restart-safe outbox for already-revoked resource files."""
import asyncio
from pathlib import Path
import re
import secrets
import stat
import time

from .cf_practice_jobs import open_db
from .account_closure_service import AUDIT_DAYS


class UnsafeResource(ValueError):
    pass


def remove_resource(root, key, kind):
    pattern = r"[a-f0-9]{48}\.(?:png|jpg|webp|jpeg)" if kind == "markdown" else r"[a-f0-9]{32}\.(?:png|jpg|webp)" if kind == "avatar" else r"[a-f0-9]{32}\.webp"
    if not re.fullmatch(pattern, key or ""):
        raise UnsafeResource("invalid_resource")
    root = Path(root).absolute()
    target = root / key
    # Reject reparse points as well as POSIX symlinks, including every parent.
    for part in [root, *root.parents, target]:
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UnsafeResource("linked_resource")
    if target.resolve().parent != root.resolve():
        raise UnsafeResource("outside_resource_root")
    try:
        if not stat.S_ISREG(target.lstat().st_mode):
            raise UnsafeResource("not_regular_file")
        target.unlink()
    except FileNotFoundError:
        pass


class ClosureCleanup:
    def __init__(self, db_path, folders):
        self.db_path, self.folders = db_path, folders
        self._event = asyncio.Event()
        self._task = None
        self._stopping = False

    async def start(self):
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="account-closure-cleanup")

    def wake(self):
        self._event.set()

    async def close(self):
        self._stopping = True
        self._event.set()
        if self._task:
            # Let an in-flight SQLite open/close or unlink finish. Cancelling
            # aiosqlite.connect can otherwise strand a connection on Windows.
            await self._task

    async def run_once(self):
        now, lease = int(time.time()), secrets.token_hex(16)
        db = await open_db(self.db_path)
        try:
            await db.execute("BEGIN IMMEDIATE")
            # Operational retention applies across restarts and disabled intake.
            await db.execute("DELETE FROM account_lifecycle_audit WHERE created_at<?", (now - AUDIT_DAYS * 86400,))
            await db.execute("DELETE FROM account_closure_requests WHERE committed_at IS NULL AND receipt_expires_at<=?", (now,))
            await db.execute("UPDATE account_closure_requests SET receipt_token_hash='' WHERE committed_at IS NOT NULL AND receipt_expires_at<=? AND receipt_token_hash<>''", (now,))
            cursor = await db.execute("SELECT * FROM account_closure_cleanup_tasks WHERE (state='pending' AND next_at<=?) OR (state='running' AND lease_until<=?) ORDER BY id LIMIT 1", (now, now))
            item = await cursor.fetchone()
            if item:
                await db.execute("UPDATE account_closure_cleanup_tasks SET state='running',lease_token=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE id=?", (lease, now + 120, now, item["id"]))
            await db.commit()
            if not item:
                return False
            state, error = "done", None
            try:
                await asyncio.to_thread(remove_resource, self.folders[item["resource_kind"]], item["resource_key"], item["resource_kind"])
            except UnsafeResource:
                state, error = "blocked", "unsafe_resource"
            except OSError:
                state, error = "pending", "file_unavailable"
            # The lease token fences a worker that resumes after another worker.
            await db.execute("BEGIN IMMEDIATE")
            await db.execute("UPDATE account_closure_cleanup_tasks SET state=?,next_at=?,lease_token=NULL,lease_until=0,last_error_code=?,updated_at=? WHERE id=? AND lease_token=?", (state, now + min(86400, 30 * 2 ** min(item["attempts"], 10)), error, now, item["id"], lease))
            await db.execute("UPDATE account_closure_requests SET cleanup_state=CASE WHEN EXISTS(SELECT 1 FROM account_closure_cleanup_tasks t WHERE t.request_id=account_closure_requests.request_id AND t.state='blocked') THEN 'attention_required' WHEN EXISTS(SELECT 1 FROM account_closure_cleanup_tasks t WHERE t.request_id=account_closure_requests.request_id AND t.state<>'done') THEN 'pending' ELSE 'completed' END WHERE request_id=?", (item["request_id"],))
            await db.commit()
            return True
        except BaseException:
            await db.rollback()
            raise
        finally:
            await db.close()

    async def _run(self):
        while not self._stopping:
            try:
                if await self.run_once():
                    continue
            except asyncio.CancelledError:
                raise
            except Exception:
                # Retry without logging resource names or account identifiers.
                pass
            if self._stopping:
                break
            self._event.clear()
            try:
                await asyncio.wait_for(self._event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass
