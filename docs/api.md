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

帖子正文按 Markdown 源文保存在数据库中，Web 端渲染前会清理 HTML。草稿属于登录成员本人，不能通过公开论坛 API 查看；保存草稿不会进入待审核队列，调用提交接口后才会转换成待审核帖子。

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
| `409` | 当前状态冲突，例如已有同步任务正在运行 |
| `429` | 登录请求过于频繁；等待后重试 |
| `503` | 服务或必要配置不可用；稍后重试或联系服务维护者 |

建议为所有请求设置超时，对 `429` 和临时 `5xx` 使用有上限的退避重试；不要对非幂等写操作盲目重试，以免重复创建数据。
