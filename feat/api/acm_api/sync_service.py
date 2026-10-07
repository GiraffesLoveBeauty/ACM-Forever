# -*- coding: utf-8 -*-
"""数据同步（增量 / 深度 / 全员）与不活跃提醒。"""
import asyncio
import time

from .cjlu_api import fetch_cjlu_submissions
from .constants import LOG, SYNC_USER_CONCURRENCY
from .crawler import Crawler
from .cf_client import binding_key


def _sync_platform_label(platform):
    return {
        "codeforces": "Codeforces",
        "luogu": "洛谷",
        "nowcoder": "牛客",
        "atcoder": "AtCoder",
        "cjlu": "校OJ",
    }.get(platform, platform)


class SyncMixin:
    async def _get_platform_sync_state(self, qq_id, platform, legacy_cursor=0):
        await self.db.execute(
            "INSERT OR IGNORE INTO user_platform_sync_state "
            "(user_qq_id, platform, cursor_timestamp, updated_at) VALUES (?, ?, ?, ?)",
            (str(qq_id), platform, int(legacy_cursor or 0), int(time.time())),
        )
        async with self.db.execute(
            "SELECT * "
            "FROM user_platform_sync_state WHERE user_qq_id=? AND platform=?",
            (str(qq_id), platform),
        ) as cursor:
            return await cursor.fetchone()

    async def _mark_platform_sync(self, qq_id, platform, status, now, *, success=False, error_code=None, error_message=None, cursor=None):
        if status == "running":
            await self.db.execute(
                "UPDATE user_platform_sync_state SET last_attempt_at=?, last_status=?, updated_at=? "
                "WHERE user_qq_id=? AND platform=?",
                (now, status, now, str(qq_id), platform),
            )
            await self.db.commit()
        elif success:
            if platform == "codeforces":
                async with self.db.execute("SELECT coverage_through_at FROM user_platform_sync_state WHERE user_qq_id=? AND platform=?", (str(qq_id), platform)) as state_cursor:
                    cf_state = await state_cursor.fetchone()
                if cf_state and cf_state["coverage_through_at"]:
                    cursor = cf_state["coverage_through_at"]
            await self.db.execute(
                "UPDATE user_platform_sync_state SET cursor_timestamp=?, last_attempt_at=?, last_success_at=?, "
                "last_status=?, last_error_code=NULL, last_error_message=NULL, consecutive_failures=0, "
                "next_retry_at=0, updated_at=? WHERE user_qq_id=? AND platform=?",
                (int(cursor or now), now, now, status, now, str(qq_id), platform),
            )
        else:
            await self.db.execute(
                "UPDATE user_platform_sync_state SET last_attempt_at=?, last_status=?, last_error_code=?, "
                "last_error_message=?, consecutive_failures=consecutive_failures+1, updated_at=? "
                "WHERE user_qq_id=? AND platform=?",
                (now, status, error_code, error_message, now, str(qq_id), platform),
            )
        await self.db.commit()

    async def _fetch_platform_with_limit(self, platform, fetcher, session, user, start_timestamp):
        semaphore = self._platform_sync_semaphores.get(platform)
        if semaphore is None:
            return await fetcher(session, user, start_timestamp, self.db, self._crawler_config())
        async with semaphore:
            return await fetcher(session, user, start_timestamp, self.db, self._crawler_config())

    async def sync_single_user(self, qq_id: str):
        lock = self._sync_user_locks.setdefault(str(qq_id), asyncio.Lock())
        if lock.locked():
            LOG.info("跳过用户 %s：已有同步任务正在运行。", qq_id)
            return False
        async with lock:
            async with self.db.execute("SELECT * FROM users WHERE qq_id = ?", (qq_id,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                return False
            current_sync_time = int(time.time())
            seven_days_ago = current_sync_time - (7 * 24 * 60 * 60)
            legacy_cursor = user["last_sync_timestamp"] or 0
            LOG.info(f"  -> 为用户 {user['name']} 执行平台独立同步...")
            user_new_count = 0
            sync_succeeded = True
            session = self._http_session
            for platform, field, fetcher in (
                ("codeforces", "cf_handle", Crawler.fetch_cf_submissions),
                ("luogu", "luogu_id", Crawler.fetch_luogu_submission),
                ("nowcoder", "nowcoder_id", Crawler.fetch_nowcoder_submissions),
                ("atcoder", "atcoder_handle", Crawler.fetch_atcoder_submissions),
                ("cjlu", "cjlu_username", fetch_cjlu_submissions),
            ):
                if not user[field]:
                    continue
                state = await self._get_platform_sync_state(qq_id, platform, legacy_cursor)
                cursor_timestamp = int(state["cursor_timestamp"] or 0)
                # 外部平台偶发延迟或请求异常时，游标可能先推进而漏掉记录。
                # AtCoder 每轮回看 7 天，已有题目由爬虫集合去重，不会重复入库。
                if platform == "codeforces" and not state["full_history_at"]:
                    start_timestamp = 0
                elif platform == "atcoder" and cursor_timestamp:
                    start_timestamp = max(0, cursor_timestamp - 7 * 86400)
                else:
                    start_timestamp = cursor_timestamp or seven_days_ago
                await self._mark_platform_sync(qq_id, platform, "running", current_sync_time)
                try:
                    result = await self._fetch_platform_with_limit(
                        platform, fetcher, session, user, start_timestamp
                    )
                    if result < 0:
                        sync_succeeded = False
                        await self._mark_platform_sync(
                            qq_id, platform, "failed", int(time.time()),
                            error_code="fetch_failed", error_message="平台抓取失败",
                        )
                    else:
                        user_new_count += result
                        await self._mark_platform_sync(
                            qq_id, platform, "success", int(time.time()),
                            success=True, cursor=current_sync_time,
                        )
                except asyncio.CancelledError:
                    await self._mark_platform_sync(
                        qq_id, platform, "cancelled", int(time.time()),
                        error_code="cancelled", error_message="同步任务已取消",
                    )
                    raise
                except Exception as exc:
                    sync_succeeded = False
                    await self._mark_platform_sync(
                        qq_id, platform, "failed", int(time.time()),
                        error_code="internal", error_message=str(exc)[:500],
                    )
                    LOG.exception("同步用户 %s 的 %s 数据失败", qq_id, field)
            if sync_succeeded:
                await self.db.execute(
                    "UPDATE users SET last_sync_timestamp = ? WHERE qq_id = ?",
                    (current_sync_time, qq_id),
                )
                await self.db.commit()
                if user_new_count > 0:
                    LOG.info(f"    为用户 {user['name']} 同步了 {user_new_count} 条新记录。")
                return True
            LOG.warning("用户 %s 同步未完全成功，保留旧同步时间以便下次重试。", qq_id)
            return False

    async def _sync_user_with_limit(self, qq_id):
        async with self._sync_user_semaphore:
            try:
                return await self.sync_single_user(qq_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                LOG.exception("自动同步用户 %s 时发生未处理异常", qq_id)
                return False

    async def sync_all_users_data(self):
        if self._sync_cycle_lock.locked():
            LOG.info("[智能同步] 已有自动或手动全量同步任务运行，本次跳过。")
            return
        async with self._sync_cycle_lock:
            LOG.info(f"[智能同步] 开始执行 {time.strftime('%H:%M')} 周期的同步任务...")
            async with self.db.execute(
                "SELECT qq_id FROM users WHERE cf_handle IS NOT NULL OR luogu_id IS NOT NULL "
                "OR nowcoder_id IS NOT NULL OR atcoder_handle IS NOT NULL OR cjlu_username IS NOT NULL"
            ) as cursor:
                user_rows = await cursor.fetchall()
            if not user_rows:
                return
            worker_count = max(1, SYNC_USER_CONCURRENCY)
            for offset in range(0, len(user_rows), worker_count):
                batch = user_rows[offset:offset + worker_count]
                await asyncio.gather(
                    *(self._sync_user_with_limit(user_row["qq_id"]) for user_row in batch),
                    return_exceptions=True,
                )
            LOG.info("[智能同步] 本次周期任务完成。")

    async def sync_single_platform_for_days(self, qq_id: str, platform: str, days: int, *, incremental=False):
        """仅同步指定用户的指定平台，不启动浏览器。"""
        lock = self._sync_user_locks.setdefault(str(qq_id), asyncio.Lock())
        if lock.locked():
            LOG.info("跳过用户 %s：已有同步任务正在运行。", qq_id)
            return None
        fetchers = {
            "cf": ("cf_handle", Crawler.fetch_cf_submissions_paginated),
            "codeforces": ("cf_handle", Crawler.fetch_cf_submissions_paginated),
            "luogu": ("luogu_id", Crawler.fetch_luogu_submission),
            "nowcoder": ("nowcoder_id", Crawler.fetch_nowcoder_submissions),
            "atcoder": ("atcoder_handle", Crawler.fetch_atcoder_submissions),
            "cjlu": ("cjlu_username", fetch_cjlu_submissions),
        }
        field_fetcher = fetchers.get(platform)
        if field_fetcher is None:
            return None
        field, fetcher = field_fetcher
        async with lock:
            async with self.db.execute("SELECT * FROM users WHERE qq_id = ?", (qq_id,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                return -1
            if not (user[field] or "").strip():
                return -2
            normalized_platform = "codeforces" if platform == "cf" else platform
            start_timestamp = 0 if days == 0 else int(time.time()) - days * 24 * 60 * 60
            state = await self._get_platform_sync_state(qq_id, normalized_platform, user["last_sync_timestamp"] or 0)
            if incremental and normalized_platform == "codeforces":
                start_timestamp = int(state["cursor_timestamp"] or 0) if (
                    state["full_history_at"] and state["coverage_through_at"]
                    and state["binding_key"] == binding_key(user)
                ) else 0
            LOG.info("  -> 为用户 %s 执行 %s 平台 [%s] 同步...", user["name"], platform, "增量刷新" if incremental and start_timestamp else "全部历史" if days == 0 else f"近{days}天")
            attempt_at = int(time.time())
            await self._mark_platform_sync(qq_id, normalized_platform, "running", attempt_at)
            session = self._http_session
            try:
                result = await self._fetch_platform_with_limit(
                    normalized_platform, fetcher, session, user, start_timestamp
                )
            except asyncio.CancelledError:
                await self._mark_platform_sync(qq_id, normalized_platform, "cancelled", int(time.time()), error_code="cancelled")
                raise
            except Exception as exc:
                await self._mark_platform_sync(qq_id, normalized_platform, "failed", int(time.time()), error_code="internal", error_message=str(exc)[:500])
                raise
            if result is not None and result >= 0:
                finished_at = int(time.time())
                if days == 0:
                    await self._mark_platform_sync(
                        qq_id, normalized_platform, "success", finished_at,
                        success=True, cursor=finished_at,
                    )
                else:
                    await self.db.execute(
                        "UPDATE user_platform_sync_state SET last_status='backfill', last_attempt_at=?, updated_at=? "
                        "WHERE user_qq_id=? AND platform=?",
                        (finished_at, finished_at, str(qq_id), normalized_platform),
                    )
                    await self.db.commit()
            else:
                await self._mark_platform_sync(qq_id, normalized_platform, "failed", int(time.time()), error_code="fetch_failed", error_message="平台抓取失败")
            return result

    async def sync_single_user_for_days(self, qq_id: str, days: int):
        """同步指定用户的各已绑定平台，返回平台到新增数量的明细。"""
        lock = self._sync_user_locks.setdefault(str(qq_id), asyncio.Lock())
        if lock.locked():
            LOG.info("跳过用户 %s：已有同步任务正在运行。", qq_id)
            return None
        async with lock:
            async with self.db.execute("SELECT * FROM users WHERE qq_id = ?", (qq_id,)) as cursor:
                user = await cursor.fetchone()
            if not user:
                return None
            requested_start = 0 if days == 0 else int(time.time()) - days * 24 * 60 * 60
            legacy_cursor = user["last_sync_timestamp"] or 0
            results = {}
            session = self._http_session
            for platform, field, fetcher in (
                ("codeforces", "cf_handle", Crawler.fetch_cf_submissions_paginated),
                ("luogu", "luogu_id", Crawler.fetch_luogu_submission),
                ("nowcoder", "nowcoder_id", Crawler.fetch_nowcoder_submissions),
                ("atcoder", "atcoder_handle", Crawler.fetch_atcoder_submissions),
                ("cjlu", "cjlu_username", fetch_cjlu_submissions),
            ):
                if not (user[field] or "").strip():
                    continue
                state = await self._get_platform_sync_state(qq_id, platform, legacy_cursor)
                cursor_timestamp = int(state["cursor_timestamp"] or 0)
                start_timestamp = requested_start if days else (cursor_timestamp or int(time.time()) - 7 * 86400)
                attempt_at = int(time.time())
                await self._mark_platform_sync(qq_id, platform, "running", attempt_at)
                try:
                    result = await self._fetch_platform_with_limit(
                        platform, fetcher, session, user, start_timestamp
                    )
                    results[platform] = result
                    if result is not None and result >= 0:
                        if days == 0:
                            finished_at = int(time.time())
                            await self._mark_platform_sync(
                                qq_id, platform, "success", finished_at,
                                success=True, cursor=finished_at,
                            )
                        else:
                            finished_at = int(time.time())
                            await self.db.execute(
                                "UPDATE user_platform_sync_state SET last_status='backfill', last_attempt_at=?, updated_at=? WHERE user_qq_id=? AND platform=?",
                                (finished_at, finished_at, str(qq_id), platform),
                            )
                            await self.db.commit()
                    else:
                        await self._mark_platform_sync(
                            qq_id, platform, "failed", int(time.time()),
                            error_code="fetch_failed", error_message="平台抓取失败",
                        )
                except asyncio.CancelledError:
                    await self._mark_platform_sync(
                        qq_id, platform, "cancelled", int(time.time()), error_code="cancelled"
                    )
                    raise
                except Exception as exc:
                    results[platform] = -4
                    await self._mark_platform_sync(
                        qq_id, platform, "failed", int(time.time()),
                        error_code="internal", error_message=str(exc)[:500],
                    )
                    LOG.exception("同步用户 %s 的 %s 数据失败", qq_id, platform)
            if results and all(value >= 0 for value in results.values()) and days == 0:
                await self.db.execute("UPDATE users SET last_sync_timestamp = ? WHERE qq_id = ?", (int(time.time()), qq_id))
                await self.db.commit()
            return results

    async def _run_bind_sync_job(self, event, qq_id: str):
        try:
            async with self._sync_cycle_lock:
                result = await self.sync_single_user_for_days(qq_id, 0)
            if not isinstance(result, dict):
                await event.reply(text="⚠️ 账号已保存，但首次同步未能完成，将在后续自动同步时重试。")
                return
            failed = [platform for platform, count in result.items() if count is None or count < 0]
            if failed:
                await event.reply(
                    text="⚠️ 账号已保存，但以下平台首次同步失败："
                    + "、".join(failed)
                    + "。后续自动同步会继续重试。"
                )
                return
            await event.reply(text="✅ 账号绑定后的全部历史记录同步已完成。")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("绑定账号后的首次同步失败: %s", qq_id)
            await event.reply(text="⚠️ 账号已保存，但首次同步失败，将在后续自动同步时重试。")

    async def _run_bind_platform_sync_job(self, event, qq_id: str, platform: str):
        """验证绑定成功后，只重新拉取刚绑定平台的全部历史记录。"""
        sync_platform = "codeforces" if platform == "cf" else platform
        try:
            async with self._sync_cycle_lock:
                count = await self.sync_single_platform_for_days(qq_id, sync_platform, 0)
            if count is None:
                await event.reply(text=f"⚠️ {_sync_platform_label(sync_platform)} 已绑定，但已有同步任务运行，将在后续自动同步时重试。")
            elif count < 0:
                await event.reply(text=f"⚠️ {_sync_platform_label(sync_platform)} 已绑定，但首次拉取做题记录失败，将在后续自动同步时重试。")
            else:
                await event.reply(text=f"✅ {_sync_platform_label(sync_platform)} 做题记录已更新，本次新增 {count} 条。")
        except asyncio.CancelledError:
            raise
        except Exception:
            LOG.exception("验证绑定后的 %s 平台首次同步失败: %s", sync_platform, qq_id)
            await event.reply(text=f"⚠️ {_sync_platform_label(sync_platform)} 已绑定，但首次拉取失败，将在后续自动同步时重试。")

    async def _check_inactive_users(self):
        now = int(time.time())
        async with self.db.execute(
            "SELECT p.qq_id, p.inactive_days, p.last_notified_at, u.name, "
            "MAX(s.submit_time) AS last_submit_time "
            "FROM notification_preferences p "
            "JOIN users u ON u.qq_id=p.qq_id "
            "LEFT JOIN submissions s ON s.user_qq_id=p.qq_id "
            "WHERE p.enabled=1 "
            "GROUP BY p.qq_id, p.inactive_days, p.last_notified_at, u.name"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            cutoff = now - int(row["inactive_days"]) * 86400
            last = row["last_submit_time"]
            if last and last >= cutoff:
                continue
            if row["last_notified_at"] and now - row["last_notified_at"] < 86400:
                continue
            try:
                await self.api.qq.post_private_msg(int(row["qq_id"]), text=f"📚 {row['name']}，你已经 {row['inactive_days']} 天没有新的已同步 AC 记录了，今天也来做一道吧！")
                await self.db.execute("UPDATE notification_preferences SET last_notified_at=? WHERE qq_id=?", (now, row["qq_id"]))
                await self.db.commit()
            except Exception:
                LOG.exception("发送不活跃提醒失败: %s", row["qq_id"])

    async def _run_sync_platform_job(self, event, qq_id: str, platform: str, days: int, task=None):
        if task:
            task["status"] = "running"
            task["started_at"] = int(time.time())
        try:
            count = await self.sync_single_platform_for_days(qq_id, platform, days)
            if task:
                task["result"] = count
                task["status"] = "completed" if count is not None and count >= 0 else "failed"
                task["finished_at"] = int(time.time())
            if count is None:
                await event.reply(text="⚠️ 当前已有该用户的同步任务运行，请稍后再试。")
            elif count == -1:
                await event.reply(text=f"❌ 找不到用户 {qq_id}。")
            elif count == -2:
                await event.reply(text=f"❌ 用户 {qq_id} 尚未绑定 {platform} 账号。")
            elif count < 0:
                await event.reply(text=f"⚠️ {platform} 平台同步失败，请查看日志。")
            else:
                await event.reply(text=f"✅ 用户 {qq_id} 的 {platform} 深度同步完成\n本次新增：{count} 条记录")
        except asyncio.CancelledError:
            if task:
                task["status"] = "cancelled"
                task["finished_at"] = int(time.time())
            raise
        except Exception:
            if task:
                task["status"] = "failed"
                task["finished_at"] = int(time.time())
            LOG.exception("用户 %s 的 %s 平台深度同步失败", qq_id, platform)
            await event.reply(text=f"❌ 用户 {qq_id} 的 {platform} 平台深度同步失败，请查看日志。")

    async def _run_sync_user_job(self, event, qq_id: str, days: int, task=None):
        if task:
            task["status"] = "running"
            task["started_at"] = int(time.time())
        try:
            result = await self.sync_single_user_for_days(qq_id, days)
            if task:
                task["result"] = result
                task["status"] = "completed" if isinstance(result, dict) else "failed"
                task["finished_at"] = int(time.time())
            if not isinstance(result, dict):
                await event.reply(text=f"❌ 用户 {qq_id} 不存在或同步被跳过。")
                return
            failed = any(count < 0 for count in result.values())
            rows = [
                (name, "失败" if count < 0 else f"新增 {count} 条记录")
                for name, count in result.items()
            ]
            image = await asyncio.to_thread(
                self._generate_table_image,
                f"用户 {qq_id} 同步结果",
                "⚠️ 部分平台失败" if failed else "✅ 全部平台同步完成",
                ("平台", "结果"),
                rows,
                (360, 970),
            )
            await self._send_image_file(
                event,
                image,
                f"sync_user_{qq_id}.png",
                "❌ 同步结果图片生成失败：字体文件不可用。",
                at_sender=False,
            )
        except asyncio.CancelledError:
            if task:
                task["status"] = "cancelled"
                task["finished_at"] = int(time.time())
            raise
        except Exception:
            if task:
                task["status"] = "failed"
                task["finished_at"] = int(time.time())
            LOG.exception("用户 %s 深度同步失败", qq_id)
            await event.reply(text=f"❌ 用户 {qq_id} 的同步任务失败，请查看日志。")
    async def _run_full_sync_job(self, event, days: int, task=None):
        if task:
            task["status"] = "running"
            task["started_at"] = int(time.time())
        if self._sync_cycle_lock.locked():
            await event.reply(text="⚠️ 当前已有同步任务运行，请稍后再试。")
            return
        async with self._sync_cycle_lock:
            try:
                async with self.db.execute("SELECT qq_id FROM users") as cursor:
                    all_users = await cursor.fetchall()
                total = len(all_users)
                for index, user_row in enumerate(all_users, 1):
                    await self.sync_single_user_for_days(user_row["qq_id"], days)
                    if index % 10 == 0 or index == total:
                        LOG.info("[全员深度同步] 进度 %d/%d", index, total)
                if task:
                    task["status"] = "completed"
                    task["finished_at"] = int(time.time())
                await event.reply(text="✅ 同步完成！正在生成榜单...")
                title = f"深度同步 · 近 {days} 天过题排行榜"
                users_data = await self._query_rank_data(days=days, limit=50)
                if not users_data:
                    await event.reply(text=f"📊 {title}\n\n该条件下暂无过题记录。")
                    return
                await self._send_rank_image(event, title, users_data)
            except asyncio.CancelledError:
                if task:
                    task["status"] = "cancelled"
                    task["finished_at"] = int(time.time())
                raise
            except Exception:
                if task:
                    task["status"] = "failed"
                    task["finished_at"] = int(time.time())
                LOG.exception("全员深度同步失败")
                await event.reply(text="❌ 全员同步失败，请查看日志。")
