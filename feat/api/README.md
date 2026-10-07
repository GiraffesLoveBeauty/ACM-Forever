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
| `ACM_CF_DATA_TTL_HOURS` | CF 练习赛选题的成员数据有效期，默认 24 小时；整数 1–720 |
| `ACM_CF_PROBLEM_TTL_HOURS` | CF 题目和比赛列表核实有效期，默认 6 小时；整数 1–720 |
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
- `/api/admin/cf/*`：管理员近期 AC 汇总、全量历史候选查重与持久化刷新任务

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

## CF 练习赛选题

管理中心的“CF 练习赛选题”入口打开 `/cf-practice.html`，仅 `admin/root` 可访问，全部 POST 沿用 Cookie 会话和 CSRF 校验。页面共用实际 `users.status` 身份范围，可排除不参赛成员；未绑定成员仍显示为待处理。近期 AC 支持日期、Rating、标签、搜索及题目 / 成员视图；候选查重使用全部历史，支持题号、CF 链接和整场比赛。

默认排除所有提交过的题，也可切换为仅排除已 AC。只有题目已核实、全员完整数据仍有效且无相应历史证据时才判为可用；其他结果分为已 AC 排除、有提交排除、未知、无效。人数按成员去重，旧 AC 也计入提交人数。只可勾选可用题目，复制前再次查重；候选清单保留在页面内，不创建比赛。详细字段与调用顺序见 [api.md（API 调用指南）](../../docs/api.md#cf-练习赛选题管理员接口)。

首次启动自动执行可重复的增量迁移：新增 CF 题目 / 比赛缓存、组任务 / 成员结果表，以及绑定版本、全量完成与覆盖时间字段。旧同步时间不会被视为全量历史完成，已有成员需先补齐历史。选题页面的普通刷新在用户锁内核对当前绑定、全量标记及覆盖时间：首次或换绑后遍历全部分页，后续使用已成功的持久化游标增量抓取。增量同步也分页，并回看七天及待判题记录；既有内部同步接口显式传入 `days=0` 时仍可强制全量。同一提交的 verdict 可更新，兼容维护修复前后的 `cf_1843A` / `1843A` AC 键，重判时校正或删除对应记录。只有全部分页成功后才更新全量标记、覆盖时间和游标，分页失败不会推进这些状态。

历史同步、题库 / 比赛资料、Web 成员详情、Bot CF 代理、账号验证和近期 AC 查询统一经过 CF 请求适配器。同一进程的同一事件循环内，请求串行执行，前一次结束后至少等待 2.1 秒，单次 30 秒超时、最多三次尝试。此限制不跨进程或事件循环共享；多 worker 部署需另设共享限流机制。

题库成功刷新时间保存在现有 `settings` 表，使用题目资料 TTL，服务重启后继续复用。元数据任务进入锁后重新检查缓存：并发等待者复用已核实题目，TTL 内不重复下载全题库；未收录候选改用对应比赛列表核实，整场展开仍要求完整比赛列表。题库格式校验通过后才在同一事务内写入题目与成功时间，失败不标记新鲜。

CF 换绑触发数据库事务内清理：删除该成员旧 CF AC、attempt、同步状态、收藏 / 题目状态、复习 / 学习计划与 CF 比赛复盘，放弃未完成 CF 挑战，并增加绑定版本。同步写入时核对版本，避免换绑或换回原账号后混入旧记录；其他平台数据保留。发布前应按既有数据库备份流程核验迁移；这些清理在实际换绑时发生，撤销源码不会恢复已清理的数据。

CF 历史同步为每次调用打开独立的数据库连接，覆盖自动同步、选题刷新及 Bot 挑战 / 训练完成入口。网络请求在分页写事务外执行；每页在同一个 `BEGIN IMMEDIATE` 事务内核对绑定、写入提交 / AC / 题目资料，最终完整性标记也在该连接上单独核验并写入。其他成员对运行时共享连接的 commit / rollback 不会结束此事务；换绑写操作与分页写入由 SQLite 写锁协调，成功换绑后清理此前的旧证据。异常或取消会回滚当前事务并关闭独立连接，避免残留写锁。

组任务与每名成员结果持久化，服务重启把未完成任务标为中断，可重新发起；任务结果领取时重新核对成员范围、当前证据与有效期。CF 失败、限流、未结束比赛或异常列表不能证明题目不存在，相关题目保持未知。两项 TTL 配置不合法时服务拒绝启动。

## 论坛首页图谱交互

欢迎栏的加权图默认展示 `s → v → d → t`，总权重为 9。鼠标悬停节点可临时预览路径；点击或触摸点选节点后，所选路径会保留，离开图谱或滚动页面不会清除选择。键盘用户可用 Tab 切换节点，Enter 或空格选中，Esc 恢复默认路径。节点提供可见焦点和路径、权重说明，点选结果通过状态区向屏幕阅读器播报；系统启用“减少动态效果”时仍可选取路径。

修改图谱时，应验证全部 12 个节点的鼠标点击、触摸点选、键盘选择与最短路径权重；同时检查悬停离开后恢复已选路径、空格不滚动页面、Esc 复位，以及窄屏和减少动态效果下的操作。

## 自助调色

所有使用共享 `app.js` 的页面均提供“自助调色”入口。基础颜色为主色、页面背景、卡片背景和强调色；高级设置可覆盖正文、次要文字、边框、链接、选中项文字及横幅背景。衍生状态和按钮前景自动计算。可选择清绿、白灰、暖黄、柔粉四个预设作为起点，也可继续完全自定义。预设仅替换正在编辑模式的草稿；另一模式、已保存主题和命名方案库保持不变。“恢复打开前的配色”可恢复当前模式，取消则恢复整个主题。

- 浅色和深色独立编辑；可选择固定模式或跟随系统。正在预览的模式与保存后的模式分别设置。
- 实时预览不写入存储；保存才写入 `localStorage` 的 `acm.theme.v1`。取消、Esc、关闭及点击面板外部恢复打开前的主题。
- 浏览器禁止存储时可选择“仅本页应用”；不提供账号或跨设备同步。
- 最多 12 个命名方案，保存在 `acm.theme.library.v1`；同名保存替换已有方案，方案库操作与当前主题保存独立。
- JSON 导入最多 32768 字节，仅接受 version/mode/light/dark 和允许的 RGB 颜色字段；导入先进入草稿，导出不包含方案库。
- 对比度面板检查列出的纯色色对，不等同整站无障碍认证。手动低对比允许保存；一键修复可能协调卡片背景，以使页面和卡片共享可读文字色。

前端测试（需要 Node.js）：

```powershell
node --test feat/api/tests/theme-colors.test.cjs feat/api/tests/theme-performance.test.cjs
```

可选浏览器验收使用 Python Playwright 和已安装的 Edge，针对单独的本地预览实例执行，不连接生产：

```powershell
python feat/api/tests/theme_browser_smoke.py
```

默认访问 `http://127.0.0.1:8088`，可用 `ACM_THEME_TEST_URL` 指定另一本地端口，浏览器通道可用 `ACM_THEME_BROWSER_CHANNEL` 更改。截图写入根目录被忽略的 `data/theme-preview.png`。前端测试尚未加入现有 GitHub Actions。

### 实时调色性能

连续输入按 `requestAnimationFrame` 合并，每帧只预览最新草稿；保存直接读取最新数据，不等待绘制。对比度搜索使用可行亮度区间与二分查找，无共同安全色时保留尽力选择并如实提示。亮度查表与有界缓存复用未变化的计算；同一帧的预览、字段和检查共享 tokens，样式变量仅在值改变时写入。调色面板打开期间暂停 CSS 过渡，关闭后恢复，避免颜色拖尾。无需 Web Worker，也不会对正文安全检查降精度。

可选性能测量（本机 Edge，预览必须在 `127.0.0.1:8088` 运行）：

```powershell
python feat/api/tests/theme_benchmark.py
# 若事先保存了修改前的 JS/CSS，可交错运行两个版本作对照：
python feat/api/tests/theme_benchmark.py --baseline-js data/theme-before-perf.js --baseline-css data/theme-before-perf.css
```

基线文件只是本地忽略的快照，不随仓库分发；没有快照时运行第一条命令即可。报告写入 `data/theme-benchmark.json`，区分颜色派生、主题帧回调 CPU、CDP 样式/布局耗时和帧间隔。每轮模拟 400 次输入，合并成 100 次预览；结果受设备、页面内容和后台负载影响，帧间隔不是 GPU 绘制耗时，也不代表固定 FPS 保证。

## 开发验证

在仓库根目录安装 `feat/api/requirements.txt` 后运行 API 集成测试：

```powershell
python -m unittest discover -s feat/api/tests -p "test_*.py"
```

GitHub Actions 会在 API 代码或测试变更的 Pull Request 和 `main` 推送上运行同一组测试。测试使用临时 SQLite 数据库，不连接生产服务器或 OJ。

CF 回归测试另覆盖成员指纹、未绑定 / 过期等就绪状态、近期与历史人数、两种查重口径、题目核实与 202 任务、权限 / CSRF、分页失败 / 中断、verdict 更新、换绑并发与持久化任务恢复。审核回归用例覆盖维护修复后的 AC 重判、组刷新使用游标及失败不推进、并发题库缓存与重启后的 TTL、异常输入 JSON 400，以及既有入口与新请求共用实际节流。跨入口集成用例同时执行成员 A 选题同步、成员 B 的 Bot 挑战 / 训练完成及 A 换绑，并验证取消分页时释放写锁；新账号空历史完成后不能残留旧 AC / attempt，查重应为可用。浏览器验收应使用独立的合成数据库和模拟 CF 适配器，检查筛选、证据分页、复制、范围变化时旧结果失效、手机布局及键盘操作；演示脚本和数据库不放进仓库。
