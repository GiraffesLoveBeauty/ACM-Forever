# 训练任务证据与同步

状态：#120 实现，依赖 #119。GET 仅读取 SQLite；发布、延期及 CF 同步状态写入后批量聚合。

| 平台 | 周期内 AC | 历史 AC | 原因 |
| --- | --- | --- | --- |
| Codeforces | 支持 | 支持 | user.status 实际时间、重复提交及完整历史覆盖 |
| AtCoder、洛谷、牛客、校 OJ | 暂不支持 | 暂不支持 | 首期未完成证据能力验收；草稿提示并阻止发布 |

周期含 starts_at 与 due_at 两端。默认开始前 AC 只显示历史已做，截止后 AC 为逾期；晚同步到的周期内 AC 可回补。历史规则允许开始前 AC，但任务未开始时不计完成。整任务需所有题完成；人数、题数、待核验和账号异常分开统计，分母始终为发布快照。

绑定 key 与账号 epoch 一致才接受新增证据。发布时未绑定者可使用第一次绑定版本；跨越多个版本视为改绑。已经确认的匿名最小证据保留，改绑不能新增新账号成绩。注销由数据库触发器清除关联标识；同 QQ 重建不能看到上一代任务。

成员接口：GET /api/me/training-tasks?tab=active|upcoming|history|all&page=1；GET /api/me/training-tasks/{id}；POST /api/me/training-tasks/{id}/refresh（空对象，202）。通过详情中的 refresh 查询本人队列状态，沿用后台同步执行器；相同运行任务去重，持久化 60 秒冷却。

管理进度接口：GET /api/admin/training-tasks/{id}/progress，支持 page/page_size、identity、status、search；GET /api/admin/training-tasks/{id}/progress/{recipient_id} 查看逐题证据。接口不接受客户端指定成员来改变授权主体。

核验读状态与已确认 AC 证据分离。聚合、管理摘要和逐题详情共用当前账号/绑定、同步状态与覆盖时间的派生规则；GET 不写进度表、不排队、不请求外部 OJ。发布时未绑定的成员首次绑定后显示 coverage_missing / pending_sync 等待同步状态，可以从任务页发起刷新；后续绑定代际仍被隔离。

有完整历史且绑定匹配时，若 coverage_through_at 小于 min(当前 UTC 秒 − 60, 截止时间)，读取即时显示 pending_sync，并计入待核验人数。摘要按接收人/平台/冻结绑定批量分组，仍为一次 SELECT，不逐成员读取。覆盖已包含整个周期的任务在结束后不会仅因时间推进失效；已有 AC 最小证据、完成成绩及核验时间均保留。
