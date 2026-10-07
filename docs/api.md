# ACM-Forever API 调用指南

本文面向 Web、机器人和其他需要读取 ACM-Forever 数据的程序调用者。代码实现是当前行为的最终依据；接口有变化时，应在同一个 PR 中更新本文和自动化测试。

## 选择接口和认证方式

| 调用方 | 接口前缀 | 认证方式 | 适用范围 |
| --- | --- | --- | --- |
| 浏览器 WebUI | `/api/*` | 登录 Cookie；写请求带 `X-CSRF-Token` | 用户资料、做题看板、训练、论坛、管理功能 |
| 受信任的服务端程序（如梓喵） | `/internal/v1/*` | `Authorization: Bearer <ACM_BOT_API_TOKEN>` | 成员数据、做题记录、排行榜、训练、同步任务等 |
| 公开只读调用方 | 部分 `/api/forum/*`、`/api/community/leaderboard` | 无 | 公开论坛内容和公开排行榜 |

不要把服务端 Token 写进网页、App、桌面程序或公开仓库。客户端应用应由自己的服务端调用内部接口，再只向客户端提供所需数据。`/internal/v1/*` 不接受 Web 登录 Cookie 代替 Bearer Token。

## 服务地址

本地默认地址为 `http://127.0.0.1:8088`。部署后将 `ACM_API_BASE_URL` 设置为实际可访问的服务根地址，例如 `https://your-domain.example`；不要在 URL 后追加 `/api` 或 `/internal/v1`，示例会自行拼接路径。

检查服务：

```http
GET /health
```

健康检查成功返回 `200` 和 `{"status":"ok"}`。机器人专用的 `GET /internal/v1/health` 需要有效 Token。

## Python：服务端调用内部 API

在调用方环境安装 `requests`（`python -m pip install requests`），并将地址和 Token 放进运行环境变量 `ACM_API_BASE_URL`、`ACM_BOT_API_TOKEN`：

```python
import os

import requests


base_url = os.environ["ACM_API_BASE_URL"].rstrip("/")
token = os.environ["ACM_BOT_API_TOKEN"]
headers = {"Authorization": f"Bearer {token}"}

response = requests.get(
    f"{base_url}/internal/v1/users/12345678/summary",
    headers=headers,
    timeout=15,
)
response.raise_for_status()
summary = response.json()
print(summary)
```

常见内部接口：

| 方法与路径 | 用途 |
| --- | --- |
| `GET /internal/v1/users/<qq_id>` | 查询成员资料 |
| `GET /internal/v1/users/<qq_id>/summary` | 查询成员做题统计摘要 |
| `GET /internal/v1/users/<qq_id>/submissions` | 查询成员做题记录 |
| `GET /internal/v1/leaderboard` | 查询排行榜 |
| `POST /internal/v1/sync/accounts/<qq_id>` | 提交指定成员的数据同步任务 |
| `GET /internal/v1/sync/tasks` | 查询同步任务状态 |

提交同步任务的请求示例：

```python
response = requests.post(
    f"{base_url}/internal/v1/sync/accounts/12345678",
    headers=headers,
    json={"platforms": ["codeforces", "nowcoder"], "days": 30},
    timeout=15,
)
if response.status_code == 202:
    task = response.json()
else:
    response.raise_for_status()
```

`platforms` 只传需要同步的平台；`days` 为回溯天数，`0` 表示按服务端策略同步。异步任务返回 `202`，之后用任务查询接口获取状态。

## Python：浏览器会话接口

`/api/*` 使用 Web 登录会话。登录成功后，服务端通过 Cookie 维持会话；登录响应中的 `csrf_token` 必须放入后续写请求的 `X-CSRF-Token` 请求头。以下示例适用于受控的 Python 服务或本地脚本，需先安装 `requests`；不要把账号密码嵌入公开客户端：

```python
import os

import requests


base_url = os.environ["ACM_API_BASE_URL"].rstrip("/")
session = requests.Session()

login = session.post(
    f"{base_url}/api/auth/login",
    json={"qq_id": os.environ["ACM_QQ_ID"], "password": os.environ["ACM_WEB_PASSWORD"]},
    timeout=15,
)
login.raise_for_status()
csrf_token = login.json()["csrf_token"]

profile = session.get(f"{base_url}/api/auth/me", timeout=15)
profile.raise_for_status()
print(profile.json())

# 所有已登录的 POST / PUT / PATCH / DELETE 写请求都要附上此请求头。
response = session.put(
    f"{base_url}/api/me/profile",
    headers={"X-CSRF-Token": csrf_token},
    json={"name": "新昵称"},
    timeout=15,
)
response.raise_for_status()
```

浏览器同源调用时，Cookie 由浏览器管理。跨域 Web 前端还需要在服务端配置精确的 `ACM_WEB_ALLOWED_ORIGINS`；不要用通配来源开放带 Cookie 的请求。

## 公开论坛 API

公开读取不需要登录：

```python
response = requests.get(
    f"{base_url}/api/forum/posts",
    params={"page": 1, "page_size": 12, "sort": "latest"},
    timeout=15,
)
response.raise_for_status()
page = response.json()  # rows、total、page、page_size
```

主要路由：

| 方法与路径 | 认证 | 说明 |
| --- | --- | --- |
| `GET /api/forum/categories` | 公开 | 论坛分类 |
| `GET /api/forum/posts` | 公开 | 帖子分页；支持 `page`、`page_size`、`sort`、`q`、`category` |
| `GET /api/forum/posts/<id>` | 公开 | 帖子详情和已发布评论 |
| `POST /api/me/avatar` | Web 登录 + CSRF | 上传当前成员头像；`multipart/form-data` 字段 `avatar`，接受 PNG/JPEG/WebP，最大 2 MB、最长边 4096 像素 |
| `DELETE /api/me/avatar` | Web 登录 + CSRF | 移除当前头像并恢复默认头像 |
| `POST /api/forum/posts` | Web 登录 + CSRF | 创建帖子；正文和标题通过审核后公开 |
| `GET /api/forum/drafts` | Web 登录 Cookie | 当前成员自己的草稿列表 |
| `POST /api/forum/drafts` | Web 登录 + CSRF | 新建草稿；`title`、`body`、`category_id` 均可暂时留空 |
| `GET /api/forum/drafts/<id>` | Web 登录 Cookie | 读取当前成员自己的草稿 |
| `PUT /api/forum/drafts/<id>` | Web 登录 + CSRF | 保存草稿修改 |
| `DELETE /api/forum/drafts/<id>` | Web 登录 + CSRF | 删除当前成员自己的草稿 |
| `POST /api/forum/drafts/<id>/submit` | Web 登录 + CSRF | 提交草稿进入人工审核；成功后草稿转为待审核帖子 |
| `POST /api/forum/posts/<id>/comments` | Web 登录 + CSRF | 评论或回复，回复可带 `parent_id` |
| `POST /api/forum/posts/<id>/like` | Web 登录 + CSRF | 切换点赞状态 |
| `POST /api/forum/posts/<id>/bookmark` | Web 登录 + CSRF | 切换收藏状态 |
| `POST /api/forum/posts/<id>/report` | Web 登录 + CSRF | 举报帖子 |

帖子列表支持 `sort=latest`、`sort=hot` 和 `sort=unanswered`。列表每页最多返回 30 条。写操作返回 JSON；发生错误时通常包含 `message`，调用方应同时检查 HTTP 状态码，不要只判断响应正文。

`GET /api/me/profile` 的 `user` 对象包含 `avatar_url`；论坛帖子列表和详情中的作者以及详情评论也包含头像地址。Web 端会在上传前自动缩放并压缩常见图片格式；直接调用 API 的客户端应自行控制文件大小。头像图片保存在服务端数据目录，并通过 `/uploads/avatars/<随机文件名>` 提供；未设置头像的前端使用 `public/assets/default-avatar.png`。

帖子正文按 Markdown 源文保存在数据库中，Web 端渲染前会清理 HTML。草稿属于登录成员本人，不能通过公开论坛 API 查看；保存草稿不会进入待审核队列，调用提交接口后才会转换成待审核帖子。

## CF 练习赛选题管理员接口

页面入口：管理中心 → CF 练习赛选题（`/cf-practice.html`）。以下接口仅支持 Web `admin/root` 会话，所有 POST 均要求 `X-CSRF-Token`；普通成员返回 403，未登录返回 401，首次改密流程沿用 428。成员身份取 `users.status`，与权限角色分开。

| 方法与路径 | 请求 / 返回 |
| --- | --- |
| `GET /api/admin/cf/options` | `statuses[{value,label,member_count}]`、`max_candidates`、`data_ttl_seconds` |
| `POST /api/admin/cf/overview` | 范围、近期筛选、分页；返回 `scope`、`rows`、`total`、`page`、`page_size`、`available_tags`、日期与覆盖时间 |
| `POST /api/admin/cf/problem-members` | 范围、`problem_id`、`period=recent/history`、日期与分页；返回成员 AC / 提交证据、时间与链接 |
| `POST /api/admin/cf/check` | 范围指纹、候选题或比赛 ID、口径；直接返回结果，或 202 + `job_id`、`preview` |
| `POST /api/admin/cf/sync` | 范围与指纹；202 + `job_id`，首次全量补齐、后续按成功游标增量刷新，维护全部历史证据及题目资料 |
| `GET /api/admin/cf/jobs/<job_id>` | 任务状态、时间、成员结果、错误与最终 `result` |

共同范围格式为 `scope: {statuses: ["现役"], exclude_qq_ids: ["12345678"]}`。身份须为实际值，最多 20 个；排除名单须属于所选身份，最多 2000 人。未绑定 CF 的成员保留在参与范围，管理员可显式排除。`scope` 返回指纹、参与 / 绑定 / 就绪 / 待处理人数、排除名单、成员明细和共同覆盖时间。

先读取概况，再使用其指纹查重：

```python
headers = {"X-CSRF-Token": csrf_token}
scope = {"statuses": ["现役"], "exclude_qq_ids": []}
overview = session.post(
    f"{base_url}/api/admin/cf/overview",
    headers=headers,
    json={"scope": scope, "days": 7, "view": "problems", "page": 1, "page_size": 20},
    timeout=15,
)
overview.raise_for_status()
response = session.post(
    f"{base_url}/api/admin/cf/check",
    headers=headers,
    json={
        "scope": scope,
        "expected_scope_fingerprint": overview.json()["scope"]["fingerprint"],
        "mode": "any_submission",
        "candidates": ["1843A", "https://codeforces.com/contest/1843/problem/B", "1843C"],
    },
    timeout=15,
)
response.raise_for_status()
if response.status_code == 202:
    job_id = response.json()["job_id"]
    # 每 2–3 秒查询一次，直到任务进入终态。
    job = session.get(f"{base_url}/api/admin/cf/jobs/{job_id}", timeout=15)
    job.raise_for_status()
else:
    result = response.json()
```

近期查询支持 `days`（默认 7；页面支持 7 / 30）或成对的 `date_from/date_to`（带时区的 ISO 8601，最大十年）；支持 `rating_min/rating_max`（0–5000）、`tag`、`search`（题号 / 题名）、`view=problems/members`。`page` 从 1 开始，`page_size` 默认 20、最大 100。缺失 Rating 返回 `null`。成员证据的 `period=history` 忽略日期，`period=recent` 使用同样日期口径。近期 AC 人数按成员与题目去重，时间取查询范围内最新 AC；历史 AC 人数包含更早证据。

查重必须携带 `expected_scope_fingerprint`；同步建议携带，证据查询也接受该字段。`candidates` 与 `contest_id` 互斥，输入最多 100 条、最多 20 场比赛；比赛 ID 为 1–9999999 的整数。题号支持 `1843A`、`1843A1`、旧键 `cf_1843A`，链接支持 codeforces.com 的 contest / gym / problemset 题目 URL。题号由后端规范化去重，无效文本（含 URL 解析失败）逐项返回 `invalid` 与原因，合法条目继续处理；已核实的比赛列表用于整场展开。`mode`、`view`、`period` 须为允许值中的字符串，数组、对象、null、布尔或数字均返回 JSON 400 `invalid_request`。

`mode=any_submission` 为默认严格模式，任何提交证据都排除；`ac_only` 仅排除 AC。查重不受近期日期、Rating、标签、搜索限制。`ac_count` 与 `attempt_count` 都是涉及成员人数，旧 AC 缺少 attempt 时仍计入两者。

| `decision` | 判定规则 | 可勾选 |
| --- | --- | --- |
| `excluded_ac` | 至少一名参与成员有 AC | 否 |
| `excluded_attempted` | 严格模式下至少一名成员有提交 | 否 |
| `unknown` | 无排除证据，但成员为空、未绑定、未补齐、过期、同步异常或题目未核实 | 否 |
| `invalid` | 输入格式无效，或新鲜的已结束比赛完整列表证明题号不存在 | 否 |
| `eligible` | 题目已核实，全员完整数据有效，无当前口径的排除证据 | 是 |

结果另含 `counts`、`total`、题名、URL、Rating、tags、`reason_code/reason`、`checked_at`、`coverage_as_of` 和范围。有效“做过”证据可直接排除；CF 失败 / 429 / 临时缺失不会被当成题目不存在。共同覆盖时间取所有参与成员的最早覆盖时间；无法完整计算时为 `null`，所有 API 时间带时区，页面按北京时间展示。结论不能覆盖同步时间之后的新提交，也不能识别只看过题的情况。

成员身份、名单、排除范围或 CF 绑定版本变化时返回 409，正文为 `{"success":false,"code":"scope_changed","message":"…"}`；客户端应清空旧结果 / 勾选，刷新范围后重新查询。后台任务领取结果也重新核对范围与数据有效期。

任务状态包括 `queued/running/completed/partial/failed/interrupted`。同步返回每名成员的 `qq_id/handle/status/error_code/error_message/finished_at`，并返回成功 / 失败人数。组任务和成员结果持久化；服务重启后未完成任务标为 interrupted。相同进行中请求合并为同一任务，同时最多接受 8 个活动任务，超过限制返回 429 `queue_full`。任务终态后停止轮询，`partial` 的查重结果仍须逐行检查 `decision`，不能默认全组成功。

普通组刷新在用户锁内核对绑定、全量标记和覆盖时间后选择抓取策略。首次、换绑或缺少完整历史时从第 1 页补齐；同一绑定已补齐后使用成功游标，增量回看七天及待判题记录。全量标记、覆盖时间和游标只在分页成功后更新，部分失败保留上次成功进度。既有内部同步接口 `days=0` 的强制全量语义保留。

提交题目的 `contestId` 缺省时跳过不可定位证据的存储，不因此拒绝整个历史分页；原始页长度和全部提交时间仍决定翻页及增量边界。可定位题号异常或分页失败仍不能标记历史完成。

历史同步使用独立连接，在每页写事务内核对绑定版本并写入证据，其他成员或 Bot 直接同步对共享连接的提交不会破坏该事务。换绑写入等待当前分页写事务结束，再原子清理旧证据；旧分页无法在清理之后重新写入。分页网络请求不持有数据库写事务，异常或取消释放独立连接及其写锁。

元数据任务在锁内复核所需题目和题库成功时间，题库 TTL 使用 `ACM_CF_PROBLEM_TTL_HOURS` 并跨服务重启保留。并发任务复用前一刷新结果；新鲜题库未收录的题目使用对应比赛核实，整场展开仍需比赛列表。失败不标记题库刷新成功。全部 CF 请求入口在同一进程 / 事件循环内共用串行节流，前一次结束后至少间隔 2.1 秒；多进程部署不共享该限制。

普通比赛列表使用仅含 `contestId` 的匿名 `contest.standings` 请求，配置密钥也不会改变这些参数。Gym（ID ≥ 100000）在 API Key / Secret 均配置时使用带 `from=1/count=1/showUnofficial=true` 的签名请求；否则尝试仅含 `contestId` 的匿名请求。访问失败继续返回未知 / partial，不生成完整比赛缓存，也不据此判断题目无效或可用。

数据有效期通过 `ACM_CF_DATA_TTL_HOURS`（默认 24）和 `ACM_CF_PROBLEM_TTL_HOURS`（默认 6）配置，两者均为 1–720 的整数。迁移后的旧同步时间不等于全量历史完成；首次补齐后才可能就绪。CF 换绑 / 解绑仅清理旧账号提交证据及同步状态、放弃进行中的 CF 挑战并增加绑定版本；收藏、笔记、题目状态、复习进度、学习计划和比赛复盘仍属于原 QQ 成员并保留，也不作为查重提交证据。启动迁移会替换旧版触发器，细节见 [README.md（独立 API 服务）](../feat/api/README.md#cf-练习赛选题)。

## 常见状态码

| 状态码 | 含义与处理 |
| --- | --- |
| `200` | 查询或操作成功 |
| `201` | 资源已创建 |
| `202` | 异步任务已接受，之后查询任务状态 |
| `400` | 请求参数或正文格式不合法；按 `message` 修正请求 |
| `401` | 缺少、失效或错误的认证信息；重新认证 |
| `403` | 权限不足或 CSRF 校验失败；确认角色并提供 CSRF Token |
| `404` | 资源不存在或当前调用方不可见 |
| `409` | 当前状态冲突，例如 CF 成员范围变化（`scope_changed`），需刷新并重新查询 |
| `429` | 登录请求过于频繁或后台任务队列已满；等待后重试 |
| `503` | 服务或必要配置不可用；稍后重试或联系服务维护者 |

建议为所有请求设置超时，对 `429` 和临时 `5xx` 使用有上限的退避重试；不要对非幂等写操作盲目重试，以免重复创建数据。
