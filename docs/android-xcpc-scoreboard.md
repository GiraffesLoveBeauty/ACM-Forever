# 管理员题单 XCPC 计分板

状态：本 PR 候选，待外部 Review。仅修改题单管理的读取展示、对应接口契约和测试，不创建 Release 或修改 Gitee/GitHub 发布源。

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
