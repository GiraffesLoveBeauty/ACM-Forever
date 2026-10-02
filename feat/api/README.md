# ACM-Forever 独立 API 服务

本服务承接梓喵 ACM Helper WebUI 的数据库访问与业务 API。SQLite 数据库由本服务独占；WebUI 和梓喵后续都通过 HTTP API 访问数据，不直接读写数据库文件。

当前包含两组接口：

- `/api/*`：移植的 WebUI API，包含登录与账号管理、成员信息、提交记录、训练与挑战、学习计划、统计分析、审核与复盘、排行榜等功能。Web 端使用 Cookie 会话和 CSRF 校验。
- `/internal/v1/*`：供受信任的梓喵服务使用的机器接口，使用 `Authorization: Bearer <ACM_BOT_API_TOKEN>` 认证，覆盖成员资料与绑定、提交和统计查询、排行榜与速报、训练和挑战、推荐题目、播报设置、账号验证及同步任务。
- `/health`：服务和数据库健康检查。

梓喵适配器通过 HTTP 客户端调用 `/internal/v1/*`，SQLite、OJ 凭据和数据同步由本服务持有。当前迁移改动仍在主题分支，生产服务切换需等代码审查、合并和服务器配置完成。

## 本地启动

在 `feat/` 目录安装 `api/requirements.txt` 中的依赖，并在当前终端设置环境变量后启动：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r api\requirements.txt
$env:ACM_WEBUI_SECRET_KEY = "本地随机密钥"
$env:ACM_DATABASE_PATH = ".\data\acm_forever.db"
python -m api
```

服务默认监听 `127.0.0.1:8088`，同时提供独立 WebUI 和 API，沿用梓喵原 WebUI 端口。生产环境通过反向代理提供 HTTPS 和访问控制；若需要通过服务器地址直接访问，应按服务器防火墙策略设置 `ACM_API_HOST`。

## 数据库与部署

设置 `ACM_DATABASE_PATH` 指向持久化 SQLite 文件。本仓库的 GitHub Actions 会将 `feat/` 同步到服务器 `/home/WYJ/acm-forever-feat`，因此生产数据库必须放在该同步目录之外，例如：

```text
/home/WYJ/acm-forever-data/acm_forever.db
```

`.db`、WAL 文件、`.env` 和密钥均被忽略，不会随代码同步。备份数据库时应一并考虑 SQLite WAL 状态，建议停服后备份或使用 SQLite 在线备份方式。

GitHub Actions 会在 `/home/WYJ/acm-forever-data/.env` 已存在时安装依赖并启动用户级 systemd 服务 `acm-forever-webui`。首次部署前，在服务器创建该环境文件，至少设置 `ACM_API_HOST`、`ACM_DATABASE_PATH`、`ACM_WEBUI_SECRET_KEY` 和 `ACM_BOT_API_TOKEN`。数据库路径应设为 `/home/WYJ/acm-forever-data/acm_forever.db`。需要通过服务器网卡访问时，将 `ACM_API_HOST` 设为 `0.0.0.0` 并在防火墙限制可访问来源；经 HTTPS 反向代理时设置 `ACM_WEBUI_COOKIE_SECURE=true`。系统服务定义位于 `deploy/acm-forever-webui.service`。首次配置还需由服务器管理员运行 `sudo loginctl enable-linger WYJ`，让用户级服务在 SSH 断开后和服务器重启后继续运行。

切换顺序：先合并并部署 ACM-Forever API，再将旧数据库安全迁入 `/home/WYJ/acm-forever-data/acm_forever.db`，配置 API 环境变量并确认服务健康；之后配置梓喵的 `ACM_BOT_API_TOKEN` 和 API 地址，再部署梓喵适配器。梓喵插件不再直接读取数据库；两端通过此服务访问同一份数据。切换期间应保留数据库备份，验证新旧功能后再清理旧数据副本。

首次启动时，服务会自动建立数据库表结构。若数据库中没有 Web 账号，可配置 `ACM_BOOTSTRAP_ROOT_QQ_ID` 和 `ACM_BOOTSTRAP_ROOT_PASSWORD` 初始化一个 root 账号；初始化成功后应移除这两个变量。也可先在环境中配置旧式管理员登录账号与密码，但应优先使用数据库账号登录。

## 环境变量

| 变量 | 用途 |
| --- | --- |
| `ACM_API_HOST` / `ACM_API_PORT` | 监听地址和端口，默认 `127.0.0.1:8088`，沿用原 WebUI 端口 |
| `ACM_DATABASE_PATH` | SQLite 数据库文件路径，默认 `./data/acm_forever.db` |
| `ACM_WEBUI_SECRET_KEY` | Web 会话签名密钥，必须设置为随机长值 |
| `ACM_WEBUI_COOKIE_SECURE` | HTTPS 反向代理时设为 `true`；直接通过受限内网 HTTP 访问时设为 `false` |
| `ACM_BOT_API_TOKEN` | `/internal/v1/*` 的服务间 Bearer Token；未设置时内部接口返回 503 |
| `ACM_BOOTSTRAP_ROOT_QQ_ID` / `ACM_BOOTSTRAP_ROOT_PASSWORD` | 空数据库首次启动时创建 root 账号；创建后移除 |
| `ACM_ROOT_QQ_IDS` / `ACM_ADMIN_QQ_IDS` | 配置 root 和初始管理员 QQ 号，多个值用逗号分隔 |
| `ACM_WEBUI_ADMIN_USERNAME` / `ACM_WEBUI_ADMIN_PASSWORD_HASH` | 可选的兼容式 Web 管理员登录配置，优先使用密码哈希 |
| `ACM_WEBUI_ADMIN_PASSWORD` | 可选兼容配置；明文密码仅用于本地临时使用，不建议部署 |
| `ACM_WEBUI_LEGACY_ADMIN_LOGIN` | 是否启用兼容式管理员登录，默认关闭 |
| `ACM_TEMP_PASSWORD_TTL_HOURS` | Web 临时密码有效期，默认 72 小时 |
| `ACM_WEB_ALLOWED_ORIGINS` | 允许携带凭据访问 API 的前端来源，逗号分隔；生产环境应精确填写 |
| `ACM_WEBUI_TRUSTED_PROXIES` | 可信反向代理 IP 列表，逗号分隔 |
| `ACM_LUOGU_COOKIE` / `ACM_LUOGU_CSRF_TOKEN` | 需要同步洛谷数据时使用 |
| `ACM_CF_API_KEY` / `ACM_CF_API_SECRET` | 需要签名访问 Codeforces API 时使用 |
| `ACM_CJLU_USERNAME` / `ACM_CJLU_PASSWORD` | 需要访问校 OJ 时使用 |

生成随机密钥示例：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 接口概览

WebUI API 以原 WebUI 路由为兼容基线。常用路由包括：

- `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- `/api/admin/web-accounts`、`/api/admin/web-accounts/<qq_id>`、`/api/admins`
- `/api/member/<qq_id>`、`/api/user`、`/api/me/profile`
- `/api/problems`、`/api/me/problems`、`/api/submissions/attempts`
- `/api/training/*`、`/api/me/training/*`、`/api/study-plan`、`/api/me/study-plan`
- `/api/stats`、`/api/leaderboard`、`/api/me/leaderboard`

Bot 服务接口包括：

- `GET /internal/v1/health`
- `/internal/v1/users/*`：成员资料、提交记录、统计、账号绑定和验证、通知偏好、随机挑战及训练
- `/internal/v1/accounts/*`：OJ 账号验证
- `/internal/v1/codeforces/*`：Codeforces 个人资料、评分记录和即将举行的比赛
- `/internal/v1/leaderboard`、`/internal/v1/rank`、`/internal/v1/reports/*`：排行榜、排名数据和速报
- `/internal/v1/recommendations/*`：推荐题目查询与维护
- `/internal/v1/sync/*`：单账号或全员同步任务的提交、查询和取消
- `/internal/v1/settings/*`、`/internal/v1/notifications/*`、`/internal/v1/challenges/*`：播报配置、提醒与月度挑战
- `/internal/v1/submissions/batch`、`/internal/v1/maintenance/*`：提交记录写入和数据维护

请求体和响应字段以接口实现为准。内部 Token 只应保存在 API 服务和梓喵服务端的环境变量中，不能放进网页代码、客户端或 Git 仓库。
