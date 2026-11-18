# 训练任务存储与发布契约

0.2.30候选扩展（待本轮PR评审）：管理进度列表可选 `order=none|completed`，缺省为 `none`，保持原顺序；响应增加 `order` 确认值。`completed` 在 identity/status/search 筛选全体后按 `completed_problems` 降序、同分保持原接收人顺序并列排名，再按 page/page_size 分页；每项增加 `rank`（例如1、1、3），不是按当前页重新从1开始。summary和冻结分母不受筛选/排序影响；非法order返回400。权限、no-store及数据库schema不变，旧客户端可忽略加法字段。范围与发布约束见[本轮说明](../android-v0.2.30-network-training.md)。以下状态行保留原阶段记录。

状态：Issue #118 / #119–#123 已实现并完成本地联调，2026-11-11；PR #124–#128 待评审，未合并、未部署。所有 PR 目标均为 main，按 #124 → #125 → #126 → #127 → #128 依次合入；涉及 feat 的合入会触发部署，前置合入期间保持能力开关关闭。

## 入口、权限和能力

管理员入口 `/admin.html?section=training` 替换原后台训练管理；成员入口 `/training-tasks.html`。原今日训练、共享 TrainingPanel、随机挑战、Bot 和移动端旧接口保留。业务身份动态读取 `users.status`，多选取并集并去重；Web 角色仅负责授权。

`ACM_TRAINING_TASKS_ENABLED` 默认 `true`，未配置时个人中心显示训练任务入口，管理员可按正常流程发布。显式设置为 `false` 并重启服务后隐藏个人中心入口，发布返回 `feature_disabled`，历史查询及证据仍保留。管理员接口要求 admin/root 会话，成员接口使用会话 QQ 和 `account_epoch`，不能指定他人；所有变更要求 CSRF，写事务内重新核验操作者。响应使用 `Cache-Control: no-store`。

Codeforces 支持 `period_ac`（周期内 AC）和 `historical_ac`（历史 AC 可计入）。洛谷公开 P 题支持历史 AC；周期模式须显式选择 `luogu_snapshot:true`，采用新增快照口径，不能证明重复 AC。其他平台可保存草稿，禁止发布。GET 仅读站内数据，刷新复用异步同步队列。

## 草稿与冻结字段

| 字段 | 契约 |
| --- | --- |
| `title` / `description` | 标题 1–100 字，省略新建标题时为“未命名训练任务”；说明最多 5000 字 |
| `statuses` | 最多 100 个业务身份字符串，发布至少一个；动态选项来自 options |
| `starts_at` / `due_at` | UTC 整数秒或带时区的 ISO 时间；开始须早于截止，界面显示 Asia/Shanghai；草稿可留空 |
| `rule` | `period_ac` 或 `historical_ac` |
| `luogu_snapshot` | 布尔值，默认 false；周期模式包含洛谷题时必须为 true；发布后冻结 |
| `problems` | 有序 `{platform, problem_id}` 数组，服务端规范化并去重；去重后最多 50 题，全部必做 |
| `version` | PATCH、DELETE、预览、发布、延期及取消均必填当前整数版本；过期返回 409，并附当前 version |

PATCH 只更新提供的白名单字段；省略字段保留，修改后版本递增并使预览失效。题目标题、难度、标签和链接由站内题库补全；没有题面仍保留原题链接和内容状态。

任务存储状态为 `draft/published/cancelled`；发布后 `phase=upcoming/active/ended` 由当前时间派生。发布事务冻结名单、发布时身份与名称、账号代际、OJ 绑定版本、题单顺序和元数据、周期和规则，并记录实际发布管理员。身份变更不补发或撤回。发布后仅允许带原因延期或取消；原截止时间、最小证据和审计记录保留。洛谷 `content_available` 是读取时批量查询的当前站内题面状态，不作为冻结内容；补采或移除题面后，重新加载管理员或成员任务详情即更新站内入口，不重写题名、题单顺序、规则或任务版本，也不请求原站。

`options.capabilities[].can_publish` 与题目 `can_publish` 保留发布能力的含义；`period_ac` 只表示精确提交时间能力，洛谷返回 false，另以 `snapshot_ac:true` 表示快照能力。题目 `supported` 根据任务规则和 `luogu_snapshot` 派生；升级前已发布且未启用快照的洛谷周期任务继续返回 `unsupported/unverified`，不自动改变原核验约定。标准题号校验、大小写及历史前缀别名、本地题面可用性和原生难度/标签展示复用现有题库工具，拒绝新建 B/T/U 题；旧草稿的非 P 题仍不能发布。

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
| `GET /{task_id}/progress` | 分页、identity、status、search（当前真实姓名、发布时昵称或 QQ）；返回不受筛选影响的 summary 与筛选后的成员 items/total |
| `GET /{task_id}/progress/{recipient_id}` | 仅管理权限，返回 recipient 与逐题 problems 证据 |

管理员进度列表 items 和逐题详情 recipient 新增 `real_name`（字符串或 null），读取当前成员资料，不改变发布时冻结的 `name`。仅未注销且账号代际匹配时返回真实姓名；未填写、注销或账号代际变化时返回 null，避免同 QQ 新账号姓名串入旧任务。该字段只在上述两个管理员接口返回，成员前台的列表/详情不新增此字段。后台完成情况使用真实姓名和题目完成进度条，未填姓名有明确提示；原有完成、核验和账号状态字段继续保留供筛选与统计使用。

预览列出未开户、停用、注销和临时凭据过期等排除原因；有效未绑定成员仍可接收。有排除项必须显式提交 `confirm_exclusions:true`。发布时事务内重新计算名单指纹，名单、绑定或账号状态变化、预览超时、版本变化均须重新确认；零题目、零有效接收人或能力不足不能发布。

`Idempotency-Key` 为 16–128 个字母、数字、下划线或连字符。同一草稿以相同 key 和发布前 version 重试，返回既有任务，不重复发放。客户端遇到超时应保留原 key；重新编辑/预览后重新准备发布。

管理进度 status 支持 `on_time/late/incomplete/not_started/timing_unknown/pending/abnormal`；identity 精确匹配发布时身份，search 匹配快照姓名或 QQ。接收人分母冻结，账号异常单列；人数完成率与题目进度分开，全部必做题完成才算整任务完成。

## 成员接口及核验

| 方法与路径 | 契约 |
| --- | --- |
| `GET /api/me/training-tasks` | tab=active（默认）/upcoming/history/all 及分页；仅本人当前账号代际的任务，含本人 recipient 进度 |
| `GET /api/me/training-tasks/{task_id}` | 本人详情、固定题单、逐题证据与 refresh 状态；他人或旧代际任务返回 404 |
| `POST /api/me/training-tasks/{task_id}/refresh` | 正文必须为 `{}`；202 返回本人任务中可核验且已绑定平台的排队任务（CF/洛谷）；相同绑定版本的运行任务复用，各平台持久化 60 秒冷却，离开页面不取消后台同步；无可核验平台的旧任务返回 409 `unsupported_verification`，不入队 |

升级前已发布且未启用快照的洛谷周期题仍返回 `verification:unsupported`、`status:unverified` 和 `evidence:null`；`unsupported_problems` 表示此类题数，不计为绑定异常或等待同步，也不参与自动完成和刷新。新发布的洛谷周期任务必须明确启用快照口径，历史 AC 任务按已确认过题集合核验。题单总数包含全部必做题；混合任务不会仅因 CF 部分完成而判定整任务完成。

CF 周期包含开始和截止两端，以 OJ 实际提交时间核验。开始前 AC 默认仅标历史已做，截止后 AC 标逾期；截止后才同步到的周期内 AC 可以回补。“历史 AC 可计入”也要等任务开始才计完成。核验、个人完成状态和任务时间阶段分别返回；无绑定、覆盖不足、同步暂停/失败及绑定变化不能被表述为确定未做。已确认的证据在同步失败后保留。

新增证据必须同时匹配账号 epoch、冻结绑定和同步覆盖绑定。发布时未绑定者只可接纳第一次绑定代际，改绑不能继承他人成绩。队列不可用或失败不清空进度；服务重启后丢失的刷新任务显示 interrupted，可重新发起。详见 [progress.md（证据核验与同步）](progress.md)。

## 错误、迁移和交付

业务错误返回 `{success:false,code,message,request_id,...details}`；401/403 沿用既有认证与 CSRF。常见 400 为 invalid_request、unsupported_capability、empty_audience、exclusions_confirmation_required；404 为 not_found；409 为 version_conflict、audience_changed、immutable_task、task_cancelled、binding_required、sync_busy；429 refresh_rate_limited 附 retry_after；503 feature_disabled 或 sync_unavailable。

新增 `training_tasks/training_task_problems/training_task_recipients/training_task_progress/training_task_audit` 和索引，重复迁移保留数据。注销触发器清除姓名、QQ、绑定标识和外部提交 ID，保留匿名最小证据和冻结分母；同 QQ 新账号不能继承旧任务。

测试、性能、备份恢复和发布回退见 [acceptance.md（联调与发布验收）](acceptance.md)。

## 洛谷快照核验与管理员审核

洛谷仅使用当前成员绑定 UID 的公开 P 题过题集合，复用成员 AC 同步。一次完整有效快照同时更新该成员的相关任务；新增 AC 数为零也需要更新负向基线。AC 与证据写入同一绑定保护事务，证据失败则一起回滚。旧 `submit_time=0` 保持未知，不生成 submission_attempts，不把 `last_success_at` 当作实际 AC 时间。任务中只有本题的状态和观察时间，不复制整份成员过题集合。

周期模式以开始后发起的有效未通过观察为下界，随后在截止前收到的有效已通过快照为按期完成依据。开始前已通过为 history_ac；首次采集晚于开始且题目已通过、或截止后首见而上次未通过观察早于截止，均为 timing_unknown。截止时或之后仍观察未通过、随后出现通过，按快照口径记逾期。请求跨越边界采用保守口径，采样时间不是实际 AC 时间。历史模式允许截止前已确认的过题，截止后首次发现同样不自动算按期。

返回的快照 evidence 包含 `accepted_at:null`、`observed_at`、`last_not_accepted_at`、`source` 和 `evidence_type:snapshot`。逐题返回 `is_ac/progress_version/review/can_review/can_clear_review/can_reset_binding`；时段不明的题计入 ac_problems 与 uncertain_problems，不计入 completed_problems。summary 增加 uncertain_count（人数）、uncertain_problem_count 与 ac_problem_count。已有本地 AC 可作为当前时点的阳性证据，不能倒填旧任务开始或截止前的证据；不允许从本地记录缺失推断未 AC。

新增 `POST /api/admin/training-tasks/{task_id}/progress/{recipient_id}/review`。正文必须包含：

```json
{"problem_id": 31, "version": 4, "task_version": 2, "decision": "on_time", "reason": "核对现场验收记录"}
```

problem_id 是训练题目行 ID，version 对应逐题 progress_version；task_version 对应任务 version。decision 为 on_time、late、clear 或 reset_binding。前两者需要冻结绑定下已有 AC 证据，原因 1–500 字并公开给成员，保留原始快照和 progress_reviewed 审计；clear 撤销已有人工决定，按原快照恢复派生结果；即使随后改绑或解绑，同一有效账号代际内仍可由管理员撤销，`can_clear_review` 单独表示该能力。没有人工决定时返回 409/review_unavailable。撤销保留原快照、绑定锚点和审计，不采纳新绑定成绩；新增完成判断仍需绑定匹配。证据版本变化返回 evidence_conflict，任务版本变化返回 version_conflict。人工证据的 accepted_at 仍为 null，evidence_type=manual。

reset_binding 仅允许管理员确认绑定变化、且本题尚未计入完成时使用。它清除该题的旧待核验证据，锚定当前 UID/绑定版本；之后需要重新同步，首次就已通过仍不能自动证明周期新增。已计入完成的旧绑定成绩保留。注销、账号代际变化、取消任务和非洛谷题不能使用该入口。

数据库采用加法迁移：training_tasks 增加 luogu_snapshot；training_task_progress 增加 snapshot_json、uncertain_json、review_json、evidence_version。旧任务不自动启用快照口径，也不补造基线。反复启动保持数据与决定。关闭功能/调度不删除证据；代码回退保留新增列，生产升级前按原发布规范备份数据库并完成分支环境验证。

延期会保留原人工决定对应的截止时间：原按期确认继续有效；原逾期确认若在新截止前已审核，可重算按期，否则回到原始快照证据判断，证据不足显示时段待确认。未开始任务不能确认完成，未截止任务不能确认逾期。
