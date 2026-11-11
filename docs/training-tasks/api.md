# 训练任务存储与发布契约

状态：Issue #118 / #119–#123 已实现并完成本地联调，2026-11-11；PR #124–#128 待评审，未合并、未部署。所有 PR 目标均为 main，按 #124 → #125 → #126 → #127 → #128 依次合入；涉及 feat 的合入会触发部署，前置合入期间保持能力开关关闭。

## 入口、权限和能力

管理员入口 `/admin.html?section=training` 替换原后台训练管理；成员入口 `/training-tasks.html`。原今日训练、共享 TrainingPanel、随机挑战、Bot 和移动端旧接口保留。业务身份动态读取 `users.status`，多选取并集并去重；Web 角色仅负责授权。

`ACM_TRAINING_TASKS_ENABLED` 默认 `false`。关闭时隐藏个人中心入口，发布返回 `feature_disabled`，历史查询及证据仍保留。管理员接口要求 admin/root 会话，成员接口使用会话 QQ 和 `account_epoch`，不能指定他人；所有变更要求 CSRF，写事务内重新核验操作者。响应使用 `Cache-Control: no-store`。

首期仅支持 Codeforces 的 `period_ac`（默认周期内 AC）和 `historical_ac`（历史 AC 可计入）。其他平台可保存草稿，在证据能力验收前禁止发布。GET 仅读站内数据，刷新复用异步同步队列。

## 草稿与冻结字段

| 字段 | 契约 |
| --- | --- |
| `title` / `description` | 标题 1–100 字，省略新建标题时为“未命名训练任务”；说明最多 5000 字 |
| `statuses` | 最多 100 个业务身份字符串，发布至少一个；动态选项来自 options |
| `starts_at` / `due_at` | UTC 整数秒或带时区的 ISO 时间；开始须早于截止，界面显示 Asia/Shanghai；草稿可留空 |
| `rule` | `period_ac` 或 `historical_ac` |
| `problems` | 有序 `{platform, problem_id}` 数组，服务端规范化并去重；去重后最多 50 题，全部必做 |
| `version` | PATCH、DELETE、预览、发布、延期及取消均必填当前整数版本；过期返回 409 |

PATCH 只更新提供的白名单字段；省略字段保留，修改后版本递增并使预览失效。题目标题、难度、标签和链接由站内题库补全；没有题面仍保留原题链接和内容状态。

任务存储状态为 `draft/published/cancelled`；发布后 `phase=upcoming/active/ended` 由当前时间派生。发布事务冻结名单、发布时身份与名称、账号代际、OJ 绑定版本、题单顺序和元数据、周期和规则，并记录实际发布管理员。身份变更不补发或撤回。发布后仅允许带原因延期或取消；原截止时间、最小证据和审计记录保留。

## 管理员接口

前缀 `/api/admin/training-tasks`。分页默认 `page=1&page_size=20`，上限 100。

| 方法与后缀 | 输入与返回 |
| --- | --- |
| `GET /options` | 返回 `enabled/statuses/capabilities/max_problems/timezone` |
| `POST /resolve-problems` | `{problems:[{platform,problem_id}]}`；最多 500 条原始输入，去重后最多 50 题；返回规范题目、逐项 errors 和 duplicates，不接受任意链接 |
| `GET /` | `state=draft|published|cancelled`、`search`、分页；返回 `items/total/page/page_size` 和任务统计 |
| `POST /` | 创建草稿，正文为草稿字段，返回详情，201 |
| `GET /{task_id}` | 详情、固定题单、接收人数和最近 50 条审计 |
| `PATCH /{task_id}` | `{version,...提供的草稿字段}`，返回更新后的详情 |
| `DELETE /{task_id}` | `{version}`；仅可删除草稿 |
| `POST /{task_id}/audience-preview` | `{version}`，查询参数分页；返回匹配 total、recipient_count、excluded_count、unbound_count、items、preview_token 和 expires_in=600 |
| `POST /{task_id}/publish` | `{version,preview_token,confirm_exclusions}`，另需 Idempotency-Key；返回已发布详情 |
| `POST /{task_id}/extend-deadline` | `{version,due_at,reason}`；新截止时间须更晚，原因 1–500 字；重算既有证据 |
| `POST /{task_id}/cancel` | `{version,reason}`；取消已发布任务，保留题单与证据 |
| `GET /{task_id}/progress` | 分页、identity、status、search；返回不受筛选影响的 summary 与筛选后的成员 items/total |
| `GET /{task_id}/progress/{recipient_id}` | 仅管理权限，返回 recipient 与逐题 problems 证据 |

预览列出未开户、停用、注销和临时凭据过期等排除原因；有效未绑定成员仍可接收。有排除项必须显式提交 `confirm_exclusions:true`。发布时事务内重新计算名单指纹，名单、绑定或账号状态变化、预览超时、版本变化均须重新确认；零题目、零有效接收人或能力不足不能发布。

`Idempotency-Key` 为 16–128 个字母、数字、下划线或连字符。同一草稿以相同 key 和发布前 version 重试，返回既有任务，不重复发放。客户端遇到超时应保留原 key；重新编辑/预览后重新准备发布。

管理进度 status 支持 `on_time/late/incomplete/not_started/pending/abnormal`；identity 精确匹配发布时身份，search 匹配快照姓名或 QQ。接收人分母冻结，账号异常单列；人数完成率与题目进度分开，全部必做题完成才算整任务完成。

## 成员接口及核验

| 方法与路径 | 契约 |
| --- | --- |
| `GET /api/me/training-tasks` | tab=active（默认）/upcoming/history/all 及分页；仅本人当前账号代际的任务，含本人 recipient 进度 |
| `GET /api/me/training-tasks/{task_id}` | 本人详情、固定题单、逐题证据与 refresh 状态；他人或旧代际任务返回 404 |
| `POST /api/me/training-tasks/{task_id}/refresh` | 正文必须为 `{}`；202 返回排队任务；重复运行任务复用，持久化 60 秒冷却，离开页面不取消后台同步 |

周期包含开始和截止两端，以 OJ 实际提交时间核验。开始前 AC 默认仅标历史已做，截止后 AC 标逾期；截止后才同步到的周期内 AC 可以回补。“历史 AC 可计入”也要等任务开始才计完成。核验、个人完成状态和任务时间阶段分别返回；无绑定、覆盖不足、同步暂停/失败及绑定变化不能被表述为确定未做。已确认的证据在同步失败后保留。

新增证据必须同时匹配账号 epoch、冻结绑定和同步覆盖绑定。发布时未绑定者只可接纳第一次绑定代际，改绑不能继承他人成绩。队列不可用或失败不清空进度；服务重启后丢失的刷新任务显示 interrupted，可重新发起。详见 [progress.md（证据核验与同步）](progress.md)。

## 错误、迁移和交付

业务错误返回 `{success:false,code,message,request_id,...details}`；401/403 沿用既有认证与 CSRF。常见 400 为 invalid_request、unsupported_capability、empty_audience、exclusions_confirmation_required；404 为 not_found；409 为 version_conflict、audience_changed、immutable_task、task_cancelled、binding_required、sync_busy；429 refresh_rate_limited 附 retry_after；503 feature_disabled 或 sync_unavailable。

新增 `training_tasks/training_task_problems/training_task_recipients/training_task_progress/training_task_audit` 和索引，重复迁移保留数据。注销触发器清除姓名、QQ、绑定标识和外部提交 ID，保留匿名最小证据和冻结分母；同 QQ 新账号不能继承旧任务。

测试、性能、备份恢复和发布回退见 [acceptance.md（联调与发布验收）](acceptance.md)。
