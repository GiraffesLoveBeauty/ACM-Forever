# ACM-Forever 独立 API 服务

本服务承接梓喵 ACM Helper WebUI 的数据库访问与业务 API。SQLite 数据库由本服务独占；WebUI 和梓喵后续都通过 HTTP API 访问数据，不直接读写数据库文件。

当前包含两组接口：

- `/api/*`：移植的 WebUI API，包含登录与账号管理、成员信息、提交记录、训练与挑战、学习计划、统计分析、审核与复盘、排行榜等功能。Web 端使用 Cookie 会话和 CSRF 校验。
- `/api/forum/*`：公开话题列表与详情、分类、搜索、热门与待回答筛选；登录成员可以发帖、评论、回复、点赞、收藏和举报。新话题进入管理员审核队列，审核与举报处理都需要 Web 管理员权限。
- `/api/community/leaderboard`：公开展示昵称、身份和各平台 AC 统计，不返回 QQ 号、真实姓名或学校字段。
- `/internal/v1/*`：供受信任的梓喵服务使用的机器接口，使用 `Authorization: Bearer <ACM_BOT_API_TOKEN>` 认证，覆盖成员资料与绑定、提交和统计查询、排行榜与速报、训练和挑战、推荐题目、播报设置、账号验证及同步任务。
- `/health`：服务和数据库健康检查。

梓喵适配器通过 HTTP 客户端调用 `/internal/v1/*`，SQLite、OJ 凭据和数据同步由本服务持有。Web 端通过 `/api/*` 调用同一服务。接口的认证方式、常用请求和 Python 示例见仓库根目录 `docs/` 中的 [api.md](../../docs/api.md)。

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

服务器当前实际使用的数据库路径、服务运行状态和梓喵接入情况，应以服务器环境文件与运行检查为准，不能仅凭仓库代码推断。若要把旧数据库切换到本服务，先停止会写入旧库的服务并制作可恢复备份（包含 WAL 状态），再设置 `ACM_DATABASE_PATH`、启动 API 并核对关键数据；确认 Web 与梓喵都经 API 正常读写后，再按运维流程停用旧写入路径。不要在没有备份和核验的情况下覆盖生产数据库。

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

接口概览只列出主要路由；参数、认证方式和可运行的 Python 示例见仓库根目录 `docs/` 中的 [api.md](../../docs/api.md)。

WebUI API 以原 WebUI 路由为兼容基线。常用路由包括：

- `POST /api/auth/login`、`POST /api/auth/logout`、`GET /api/auth/me`
- `/api/admin/web-accounts`、`/api/admin/web-accounts/<qq_id>`、`/api/admins`
- `/api/member/<qq_id>`、`/api/user`、`/api/me/profile`
- `POST /api/me/avatar`、`DELETE /api/me/avatar`：当前成员头像上传与重置
- `/api/problems`、`/api/me/problems`、`/api/submissions/attempts`
- `/api/training/*`、`/api/me/training/*`、`/api/study-plan`、`/api/me/study-plan`
- `/api/stats`、`/api/leaderboard`、`/api/me/leaderboard`

论坛常用路由包括：

- `GET /api/forum/categories`、`GET /api/forum/posts`、`GET /api/forum/posts/<id>`
- `POST /api/forum/posts`、`POST /api/forum/posts/<id>/comments`
- `POST /api/forum/posts/<id>/like`、`POST /api/forum/posts/<id>/bookmark`、`POST /api/forum/posts/<id>/report`
- `GET /api/forum/mine/posts`、`GET /api/forum/mine/bookmarks`
- 管理员审核：`GET /api/forum/moderation/posts`、`POST /api/forum/moderation/posts/<id>` 和举报处理接口

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

`/api/*` 面向 Web 会话用户，`/internal/v1/*` 是受信任服务之间的接口。内部 Token 只应保存在 API 服务和梓喵服务端的环境变量中，不能放进网页代码、桌面或移动客户端、公开示例和 Git 仓库。修改接口时，应同步更新调用指南与相关自动化测试。

## 论坛首页图谱交互

欢迎栏的加权图默认展示 `s → v → d → t`，总权重为 9。鼠标悬停节点可临时预览路径；点击或触摸点选节点后，所选路径会保留，离开图谱或滚动页面不会清除选择。键盘用户可用 Tab 切换节点，Enter 或空格选中，Esc 恢复默认路径。节点提供可见焦点和路径、权重说明，点选结果通过状态区向屏幕阅读器播报；系统启用“减少动态效果”时仍可选取路径。

修改图谱时，应验证全部 12 个节点的鼠标点击、触摸点选、键盘选择与最短路径权重；同时检查悬停离开后恢复已选路径、空格不滚动页面、Esc 复位，以及窄屏和减少动态效果下的操作。

## 自助调色

所有使用共享 `app.js` 的页面均提供“自助调色”入口。基础颜色为主色、页面背景、卡片背景和强调色；高级设置可覆盖正文、次要文字、边框、链接、选中项文字及横幅背景。衍生状态和按钮前景自动计算，不再从固定模板中选择。

- 浅色和深色独立编辑；可选择固定模式或跟随系统。正在预览的模式与保存后的模式分别设置。
- 实时预览不写入存储；保存才写入 `localStorage` 的 `acm.theme.v1`。取消、Esc、关闭及点击面板外部恢复打开前的主题。
- 浏览器禁止存储时可选择“仅本页应用”；不提供账号或跨设备同步。
- 最多 12 个命名方案，保存在 `acm.theme.library.v1`；同名保存替换已有方案，方案库操作与当前主题保存独立。
- JSON 导入最多 32768 字节，仅接受 version/mode/light/dark 和允许的 RGB 颜色字段；导入先进入草稿，导出不包含方案库。
- 对比度面板检查列出的纯色色对，不等同整站无障碍认证。手动低对比允许保存；一键修复可能协调卡片背景，以使页面和卡片共享可读文字色。

前端测试（需要 Node.js）：

```powershell
node --test feat/api/tests/theme-colors.test.cjs
```

可选浏览器验收使用 Python Playwright 和已安装的 Edge，针对单独的本地预览实例执行，不连接生产：

```powershell
python feat/api/tests/theme_browser_smoke.py
```

默认访问 `http://127.0.0.1:8088`，可用 `ACM_THEME_TEST_URL` 指定另一本地端口，浏览器通道可用 `ACM_THEME_BROWSER_CHANNEL` 更改。截图写入根目录被忽略的 `data/theme-preview.png`。前端测试尚未加入现有 GitHub Actions。

## 开发验证

在仓库根目录安装 `feat/api/requirements.txt` 后运行 API 集成测试：

```powershell
python -m unittest discover -s feat/api/tests -p "test_*.py"
```

GitHub Actions 会在 API 代码或测试变更的 Pull Request 和 `main` 推送上运行同一组测试。测试使用临时 SQLite 数据库，不连接生产服务器或 OJ。
