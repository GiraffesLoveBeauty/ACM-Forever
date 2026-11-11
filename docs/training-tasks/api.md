# 训练任务存储与发布契约

状态：Issue #118 / #119 实现分支，需按 #119 → #120 → #121、#122 → #123 的顺序评审合入。所有 PR 目标均为 main，合入涉及 feat 的改动会自动部署，本分支不执行发布。

训练任务独立于今日训练和同步队列。管理员入口为 /admin.html?section=training，成员入口为 /training-tasks.html。users.status 动态选人、并集去重；Web 角色只负责授权。发布以事务冻结名单、账号代际、题单顺序、周期和完成规则，预览失效返回 409。

首期核验能力为 Codeforces 的周期内 AC 与历史 AC 两种规则。其他平台允许保留在草稿，但在能力未验证前禁止发布。实际提交时间使用 UTC 秒，界面显示 Asia/Shanghai。

管理接口前缀 /api/admin/training-tasks：options、列表/创建、详情/草稿编辑/删除、resolve-problems、audience-preview、publish、extend-deadline、cancel。成员与进度接口在 #120 补齐。所有变更操作沿用会话、CSRF，事务内重新核验管理员权限。发布要求 version、preview_token、Idempotency-Key；有排除成员须显式确认。

ACM_TRAINING_TASKS_ENABLED 默认为 false，用于兼容部署后再开放发放和成员入口。关闭时保留历史查询，禁止新增发放。已发布仅可带原因延期或取消，禁止改题、减员、缩短周期和人工勾 AC。

迁移只新增训练任务表和索引，不删除历史表；重复启动应保持数据。注销保留匿名任务证据和冻结分母，清除姓名、QQ、绑定标识等关联信息。验收与回退记录见后续 #123 文档。
