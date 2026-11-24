# 管理员题单 XCPC 计分板

状态：基础计分板已在当前代码中。本文件末尾记录 2026-11-24 的本地展示优化，提请外部 Review，尚未合并或发布。该优化不改变后端契约、排名规则或 Gitee/GitHub 发布源。

管理员进入题单的“完成情况”后，仍可按姓名、QQ、身份和完成状态筛选。页面增加 XCPC 风格展示：

- 左侧固定排名和成员信息。
- 中间显示题目列；题目少时保持紧凑，题目多时只允许中间区域横向滑动。
- 右侧固定通过题数和罚时。
- 默认沿用“不排名”，选择“按完成数量排名”时沿用服务器全体筛选后的全局名次和并列规则。
- `+1` 表示服务器已经核验通过，`?` 表示待核验/状态不确定，`—` 表示当前没有完成证据。客户端不凭空显示错误提交次数。

## 接口

管理员读取既有接口时附加 `view=xcpc`：

```text
GET /api/admin/training-tasks/{id}/progress
    ?page=1&page_size=20&search=&identity=&status=&order=none|completed&view=xcpc
```

响应保留原 `summary`、`items`、`total`、`order` 字段，并增加 `scoreboard`，其中包含 `columns`、`rows` 和 `penalty_definition`。每一行包含 `rank`、`completed_problems`、`problem_count`、`penalty_minutes` 及与题目列对应的 `cells`。

罚时只使用已有的核验通过时间。历史 AC 不计入本题单时间罚时，未知提交次数显示状态而不猜测。未部署该接口的旧服务器没有 `scoreboard` 时，App 保留原成员卡片列表，不能把普通列表冒充 XCPC 计分板。

## 验收

覆盖服务端全局排序和并列、筛选后排名、管理员权限、接口响应字段、Android 真实管理员页面、固定两侧与中间横向题目区域、题目状态和返回流程。测试数据使用合成账号与拦截 HTTPS，不访问生产账号。

## 2026-11-24：姓名、首次 AC 与罚时（1.0.3 Review 候选）

- 管理员题单 → 完成情况：用户名下方显示 `real_name`；为空时显示“未填写姓名”。长名字在固定列内省略，点题详情显示完整名字。
- 每道题的格子均可点击，直接使用当前响应的 `rows[].cells[]` 和对应 `columns[]` 显示题目、核验状态、首次已核验 AC 时间及本题罚时，不追加网络请求、不刷新计分板。
- 时间以北京时间显示到秒。这里的“首次”是当前题单采用的首次已核验 AC 证据，不能描述成平台全部历史的最早提交。
- 已通过但 `accepted_at` 为 0/null/缺失的历史记录明确显示“接口未提供时间”，不显示 1970 年。待核验或无证据不显示 AC 日期，也不伪造本题罚时。
- 右侧明确显示“罚时 N 分”，采用服务器 `penalty_minutes`；缺失时显示“罚时 —”。本题罚时从题单开始到该次 AC 的分钟数向下取整，题单开始前及无时间的历史 AC 不计罚时；缺少开始时间时不计算本题用时。
- **缺失数据**：现有 API 没有首次 AC 前的错误提交次数，无法计算标准 XCPC 的每次错误提交加罚 20 分钟。页面及详情均注明不含错误提交加罚。本次不扩大后端数据采集范围。
- 保留默认不排名、服务器全体筛选后按完成数量给出的名次与并列规则；不在当前分页内追加罚时排序。
- 仅修改可选管理员模块的展示逻辑，普通成员不新增真实姓名访问入口。固定左侧由 172dp 收窄到 124dp，固定右侧由 108dp 收窄到 88dp，中间继续横向滚动。

对应代码：`AdminTrainingActivity`、可选管理员模块内的 `TrainingScoreboardData`。单元测试覆盖时区、缺失时间、待核验、历史 AC、缺失累计罚时及超过一天的用时；`TrainingTasksUiSmoke` 补充真实页面姓名、点题详情与不额外读取计分板的验证。

本轮本地验证（2026-11-24）：

- 独立分支基于 `main`（`11c4ace3547b`），不包含暂停的更新源修改。
- `:admin:testDebugUnitTest`：12 项通过，其中本次新增 9 项。
- `:app:testDebugUnitTest`：256 项，253 项通过、3 项跳过，无失败。
- `test_release_credits.py`：7 项通过，核对署名、头像和版本日志。
- `:app:assembleDebug`、`:admin:assembleDebug`、`:advanced:assembleDebug`、`:app:assembleDebugAndroidTest`：构建通过。
- `:app:lintDebug`：通过，包含管理员模块分析。
- `git diff --check`：通过。
- 当前无已连接模拟器或手机，`TrainingTasksUiSmoke` 本轮仅编译，尚未在设备执行；未访问生产账号或验证生产部署。

本机离线构建使用已缓存的 AGP 对应 AAPT2 可执行文件覆盖 Maven 查找（`android.aapt2FromMavenOverride`），未修改仓库构建配置。以上是本地验证，不代替外部 Review。
