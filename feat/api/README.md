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

前端已迁移到 `../web` 中的 Vue 3 + Vite。开发时另开终端在 `feat/web` 执行 `pnpm install --frozen-lockfile`、`pnpm dev`，访问 `127.0.0.1:5173`。要在 `8088` 访问完整网站，先执行 `pnpm build`；服务读取 `feat/web/dist`，没有构建制品时页面返回 `503`，API 不受影响。部署工作流会自动构建并同步制品。详见 [Vue 前端 README](../web/README.md)。

## 数据库与部署

设置 `ACM_DATABASE_PATH` 指向持久化 SQLite 文件。本仓库的 GitHub Actions 会将 `feat/` 同步到服务器 `/home/WYJ/acm-forever-feat`，因此生产数据库必须放在该同步目录之外，例如：

```text
/home/WYJ/acm-forever-data/acm_forever.db
```

`.db`、WAL 文件、`.env` 和密钥均被忽略，不会随代码同步。备份数据库时应一并考虑 SQLite WAL 状态，建议停服后备份或使用 SQLite 在线备份方式。

GitHub Actions 会在 `/home/WYJ/acm-forever-data/.env` 已存在时安装依赖并启动用户级 systemd 服务 `acm-forever-webui`。首次部署前，在服务器创建该环境文件，至少设置 `ACM_API_HOST`、`ACM_DATABASE_PATH`、`ACM_WEBUI_SECRET_KEY` 和 `ACM_BOT_API_TOKEN`。数据库路径应设为 `/home/WYJ/acm-forever-data/acm_forever.db`。需要通过服务器网卡访问时，将 `ACM_API_HOST` 设为 `0.0.0.0` 并在防火墙限制可访问来源；经 HTTPS 反向代理时设置 `ACM_WEBUI_COOKIE_SECURE=true`。系统服务定义位于 `deploy/acm-forever-webui.service`。首次配置还需由服务器管理员运行 `sudo loginctl enable-linger WYJ`，让用户级服务在 SSH 断开后和服务器重启后继续运行。

服务器当前实际使用的数据库路径、服务运行状态和梓喵接入情况，应以服务器环境文件与运行检查为准，不能仅凭仓库代码推断。若要把旧数据库切换到本服务，先停止会写入旧库的服务并制作可恢复备份（包含 WAL 状态），再设置 `ACM_DATABASE_PATH`、启动 API 并核对关键数据；确认 Web 与梓喵都经 API 正常读写后，再按运维流程停用旧写入路径。不要在没有备份和核验的情况下覆盖生产数据库。

首次启动时，服务会自动建立数据库表结构。若数据库中没有 Web 账号，可配置 `ACM_BOOTSTRAP_ROOT_QQ_ID` 和 `ACM_BOOTSTRAP_ROOT_PASSWORD` 初始化一个 root 账号；初始化成功后应移除这两个变量。也可先在环境中配置旧式管理员登录账号与密码，但应优先使用数据库账号登录。

### 单独初始化数据库与题目采集

安装 API 依赖后，可以在服务器部署目录执行初始化，无需启动 HTTP 服务，也无需设置 Web 会话密钥：

```bash
cd /home/WYJ/acm-forever-feat
python3 -m api.init_db --database /home/WYJ/acm-forever-data/acm_forever.db
```

省略 `--database` 时读取 `ACM_DATABASE_PATH`，未配置时使用当前目录的 `./data/acm_forever.db`。命令初始化服务所需的表结构与默认设置，可重复运行，保留已有业务数据；root 账号仍由服务启动时的配置创建。正常启动也会自动执行相同的表结构初始化。

管理员在 **管理后台 → 题库管理 → 拉取题目** 中选择平台、填写比赛 ID 和题数，点击 **开始拉取**，即可触发服务器抓取公开 AtCoder 或 Codeforces 比赛的新题目。支持选填题号、选择题面语言和刷新已有题目；页面显示进度与失败原因，成功后自动刷新题库。离开页面后任务继续执行，可在 **同步任务** 查看或取消。

同一页面的 **初始化数据库** 按钮补齐服务端 SQLite 表结构并显示平台题库统计，保留已有数据。选择 **拉取范围 → 该平台全部题目** 后无需填写比赛 ID，服务器先导入公开目录，再按 **每批处理题数** 自动拉取所有题面与样例；每批题数不限制总数量。默认跳过成功题目，取消或重启后再次运行可继续未完成题目并重试失败题目。全量任务逐题限速，可能运行数小时。

网页调用 `POST /api/admin/problems/sync`，使用现有 Web `admin/root` 会话与 CSRF，返回 202 和任务 ID，进度及取消复用 `/api/tasks`。题目正文与样例写入同一条 `crawler_problems` 记录，并原子更新 `recommendations`，使既有题库列表能够展示新题目。默认跳过成功题目，可显式刷新；失败保留已有正文和样例。CF 当前支持普通公开比赛，题号兼容 `1843A/cf_1843A`，与既有提交记录统一存为 `cf_1843A`；元数据和页面共用 CF 请求节流。详细参数和调用示例见 [API 调用指南](../../docs/api.md#管理员采集新题目)。

CF 支持没有样例的题目及直接返回 PDF 的题面。PDF 原文件存入 SQLite，详情页通过本站接口打开，图示与样例保留在 PDF 中，暂不拆分为结构化样例。启动或初始化时自动给旧题库补充 `statement_pdf BLOB` 列，不清空数据；失败记录可再次按比赛 / 指定题号采集，默认只跳过成功题目。

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
- `/api/admin/members`：成员搜索与分页
- `/api/problems`、`/api/me/problems`：题库查询和收藏；各自的 `/<platform>/<problem_id>` GET 接口读取已采集题面与样例。列表的“打开题目”进入 `/problem.html` 站内详情页，支持公式与样例复制；仅有目录时显示等待采集提示。图片仍由原站 HTTPS 加载。
- `/api/training/*`、`/api/me/training/*`、`/api/contest/reviews`、`/api/me/contest/reviews`
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

## 统一管理后台

管理员统一从 `/admin.html` 进入。左侧菜单和顶部修改密码、主题、退出、自助调色保持固定，Vue Router 根据查询参数切换右侧 Vue 组件。后台菜单不读取历史 `nav_order` / `nav_hidden` 配置，字号设置仍可使用。

| 地址 | 功能 |
| --- | --- |
| `/admin.html` | 成员账号：批量发放、创建、启停、密码重置、Web 角色 |
| `/admin.html?section=members` | 成员搜索和分页；附 `qq_id` 进入详情，保留 `search/page` 返回列表 |
| `/admin.html?section=training` | 按成员、平台、难度生成训练和查看挑战历史 |
| `/admin.html?section=problems` | 题目查询、筛选、分页、收藏和打开题目 |
| `/admin.html?section=cf-practice&tab=check` | CF 候选查重；`tab=recent` 为近期刷题 |
| `/admin.html?section=contests` | 比赛题目和逐题状态；可附 `qq_id/contest_id` |
| `/admin.html?section=tasks` | 同步队列、执行结果、失败原因、取消和刷新 |
| `/admin.html?section=moderation&tab=reports` | 举报处理；`tab=posts` 为话题审核 |
| `/admin.html?section=settings` | 外观、比赛播报、QQBot 管理员 |

直接打开、刷新、前进后退均按地址恢复模块。CF 默认分区初始化不额外新增历史项；主动点击或用键盘切换分区才新增历史项，从侧栏进入 CF 后按一次后退可回到原模块。未知 `section` 回到成员账号并提示；不合法的 `tab/qq_id` 清理后显示默认分区或列表。Web 角色仅在成员账号维护；成员详情显示 Web 角色，不再修改权限。QQBot 管理员名单在全局设置维护，与 Web 角色分别存储，只有 Web root 可写。

每个功能模块通过 Vue 组件与 `feat/web/src/lib/api.js` 管理请求、监听器和定时器的生命周期。离开时取消页面查询和轮询，旧响应不会替换新模块。账号发放结果切换前提示复制，离开后清除临时密码，不写入模块缓存、浏览历史或浏览器存储。CF 已提交的后台任务继续运行；`feat/web/src/lib/admin.js` 在模块内存中保存待确认提交，提交确认请求独立于组件生命周期，最多等待 30 秒，沿用公共 API 的会话与 CSRF 校验。确认回调只保存任务编号或错误；同一后台页面内切换模块后返回，恢复同一个任务的轮询并重新核验候选结果，等待确认与执行期间禁用重复同步和候选操作。任务即使在返回前已完成也不会重新提交；确认失败在当前或返回后的 CF 模块显示错误并允许重试。该内存不跨整页刷新或关闭保存。

普通成员导航仅保留论坛、排行榜、个人中心。个人中心保留最近 AC 摘要和今日训练、题库、赛事复盘入口；管理员打开这些共用旧路径会转入后台对应模块，普通成员继续使用前台。旧成员详情地址保留 `qq_id`；登录、强制改密保留目标路径及参数。普通成员访问后台页面仍由服务端返回 403，各业务接口保持权限和 CSRF 校验。

待复习 / 待复盘、提交时间线、笔记与计划工作区已下线。旧 `reviews.html/submissions.html/workspace.html` 显示“功能已下线”，提供个人中心和管理中心入口；专属 Web API 返回 410，详见 [api.md（API 调用指南）](../../docs/api.md#已下线的-web-功能)。历史笔记、复习、计划表保留存档，无删除表或数据迁移；换绑清理提交证据时也保留学习资料。提交记录与提交尝试继续保存和同步，供排行榜、训练统计、CF 查重及机器人使用。CF 同步和赛事状态更新不再创建复习队列或计划条目。

验收应覆盖九个模块、成员列表 / 详情、地址刷新和前进后退、登录 / 改密回跳、账号发放退出清理、同步轮询停止 / 恢复、CF 复制前复核、两种角色的旧入口、窄屏深浅主题。CF 回归还应验证默认菜单入口一次后退离开、用户分区切换的前进后退，以及同步已接受但确认延迟期间反复退出 / 返回、返回前任务完成、确认失败后重试。核心接口与 Web 单元测试命令如下，现有 API 自动检查同时运行这些 Web 单元测试：

```powershell
python -m unittest discover -s feat/api/tests -p "test_*.py"
node --test feat/api/tests/admin-history.test.cjs feat/api/tests/admin-problem-sync.test.cjs feat/api/tests/cf-sync.test.cjs feat/api/tests/theme-colors.test.cjs feat/api/tests/theme-performance.test.cjs
```

本地浏览器联调、演示数据库和截图应置于仓库外，使用合成数据和模拟 OJ 响应。当前服务器工作流在 `feat/**` 改动合并 `main` 后自动部署，合并前仍需跨人评审、联调验收及运维确认。

## CF 练习赛选题

管理中心的“CF 练习赛选题”入口打开 `/admin.html?section=cf-practice`，旧 `/cf-practice.html` 自动转入该模块，仅 `admin/root` 可访问，全部 POST 沿用 Cookie 会话和 CSRF 校验。页面共用实际 `users.status` 身份范围，可排除不参赛成员；未绑定成员仍显示为待处理。近期 AC 支持日期、Rating、标签、搜索及题目 / 成员视图；候选查重使用全部历史，支持题号、CF 链接和整场比赛。

默认排除所有提交过的题，也可切换为仅排除已 AC。只有题目已核实、全员完整数据仍有效且无相应历史证据时才判为可用；其他结果分为已 AC 排除、有提交排除、未知、无效。人数按成员去重，旧 AC 也计入提交人数。只可勾选可用题目，复制前再次查重；候选清单保留在页面内，不创建比赛。详细字段与调用顺序见 [api.md（API 调用指南）](../../docs/api.md#cf-练习赛选题管理员接口)。

首次启动自动执行可重复的增量迁移：新增 CF 题目 / 比赛缓存、组任务 / 成员结果表，以及绑定版本、全量完成与覆盖时间字段。旧同步时间不会被视为全量历史完成，已有成员需先补齐历史。选题页面的普通刷新在用户锁内核对当前绑定、全量标记及覆盖时间：首次或换绑后遍历全部分页，后续使用已成功的持久化游标增量抓取。增量同步也分页，并回看七天及待判题记录；既有内部同步接口显式传入 `days=0` 时仍可强制全量。同一提交的 verdict 可更新，兼容维护修复前后的 `cf_1843A` / `1843A` AC 键，重判时校正或删除对应记录。只有全部分页成功后才更新全量标记、覆盖时间和游标，分页失败不会推进这些状态。

CF `Problem.contestId` 为可选字段。缺少该字段的非比赛题目无法映射到候选 CF 题号，历史同步跳过其提交、AC 和题目缓存写入；分页长度及增量时间边界仍使用完整原始页，避免漏掉后续合法提交。完整遍历成功后仍可标记历史完成；可定位题目的题号错误、异常提交时间或分页失败继续阻止完成标记。

历史同步、题库 / 比赛资料、Web 成员详情、Bot CF 代理、账号验证和近期 AC 查询统一经过 CF 请求适配器。同一进程的同一事件循环内，请求串行执行，前一次结束后至少等待 2.1 秒，单次 30 秒超时、最多三次尝试。此限制不跨进程或事件循环共享；多 worker 部署需另设共享限流机制。

题库成功刷新时间保存在现有 `settings` 表，使用题目资料 TTL，服务重启后继续复用。元数据任务进入锁后重新检查缓存：并发等待者复用已核实题目，TTL 内不重复下载全题库；未收录候选改用对应比赛列表核实，整场展开仍要求完整比赛列表。题库格式校验通过后才在同一事务内写入题目与成功时间，失败不标记新鲜。

普通公开比赛的 `contest.standings` 请求只携带 `contestId`，即使配置了 API 密钥也不签名。按现有题目 URL 约定，ID ≥ 100000 的 Gym 比赛在 `ACM_CF_API_KEY` 与 `ACM_CF_API_SECRET` 均配置时使用签名请求，并携带 `from=1/count=1/showUnofficial=true`；缺少完整凭据时尝试仅含 `contestId` 的匿名请求。私有比赛或无访问权限的 Gym 请求失败时不写入完整比赛缓存，不据此判断题目无效或可用。

CF 换绑 / 解绑在数据库事务内删除该成员旧 CF AC、attempt 与同步状态，放弃未完成 CF 挑战，并增加绑定版本；收藏、题目状态、笔记、复习进度、学习计划及比赛复盘属于 QQ 成员个人资料，全部保留。Web 与 Bot 清理入口采用同一规则，其他平台数据保留。同步写入时核对版本，避免换绑或换回原账号后混入旧记录；保留的个人资料不作为旧账号提交证据参与选题查重。数据库初始化在同一事务内替换旧版换绑触发器，可重复执行且不改动已有绑定或个人资料。发布前应按既有数据库备份流程核验迁移；旧版已删除的记录不能由本次迁移自动恢复，需从备份恢复。

CF 历史同步为每次调用打开独立的数据库连接，覆盖自动同步、选题刷新及 Bot 挑战 / 训练完成入口。网络请求在分页写事务外执行；每页在同一个 `BEGIN IMMEDIATE` 事务内核对绑定、写入提交 / AC / 题目资料，最终完整性标记也在该连接上单独核验并写入。其他成员对运行时共享连接的 commit / rollback 不会结束此事务；换绑写操作与分页写入由 SQLite 写锁协调，成功换绑后清理此前的旧证据。异常或取消会回滚当前事务并关闭独立连接，避免残留写锁。

组任务与每名成员结果持久化，服务重启把未完成任务标为中断，可重新发起；任务结果领取时重新核对成员范围、当前证据与有效期。CF 失败、限流、未结束比赛或异常列表不能证明题目不存在，相关题目保持未知。两项 TTL 配置不合法时服务拒绝启动。

## 论坛首页布局

首页使用独立的三栏布局：左侧社区介绍与快捷入口、中间讨论区、右侧热门话题与社区公约。外层网格不绘制公共背景或边框，讨论区和两侧卡片分别呈现；首页布局样式位于 `public/assets/forum-home-layout.css`。

视口宽度不超过 1200px 时，右侧信息移到讨论区下方；不超过 900px 时，讨论区、左侧介绍、右侧信息按单列排列；不超过 600px 时，侧栏内部卡片也改为单列。窄屏仍显示两侧内容和快捷入口，版块列表保留横向滚动；不超过 480px 时，顶部品牌、账号操作和导航分行显示。

### 工业视觉设计

论坛首页、话题页、发帖页、排行榜、个人中心和登录页使用 `public/assets/endfield-theme.css`，通过 `endfield-design` 页面类限定布局与装饰的作用范围。采用无衬线字体、直角边框、深色欢迎横幅和黄色操作入口；首页保留独立左右侧栏，横幅内的加权图使用原有 SVG 交互，并补充跳到讨论列表的键盘入口。字体使用系统字体栈，不请求外部字体；装饰由 CSS 和现有 SVG 绘制。

视觉参考为[终末地官方网站](https://endfield.hypergryph.com/#information)，并调研了[cloud-oc/endspace](https://github.com/cloud-oc/endspace/tree/theme) 的工业界面主题和[jambochen/endfield-calc](https://github.com/jambochen/endfield-calc) 的生产链信息组织。当前实现为本仓库原有前端上的样式与结构调整，未引入这些项目的组件、依赖或游戏素材。

新访客默认使用“工业黄”的浅色/深色方案，并跟随系统模式。已有 `acm.theme.v1` 配色仍按保存值加载；可以在自助调色中选择“工业黄”。样式调整不改变话题请求、登录校验或后端数据结构。

按钮交互参考 [FZ Wiki](https://www.fz.wiki/) 的短促位移和强调色边线：主发帖入口带扫光和图标位移，普通按钮上浮 2px，导航与排序按钮展开强调线，版块入口突出边线并移动图标。按下时回到原位，变化不占用布局空间。鼠标悬停仅在支持精确指针的设备上触发；键盘焦点保留清晰外框，禁用按钮不产生位移，系统“减少动态效果”下关闭过渡、扫光及位移动画。实现使用原生 CSS，无新增依赖。

欢迎横幅的左上、右下采用半调圆点，参考 [Rahoo 素材生成器](https://rahoo.online/) 的“半调波点”和 FZ Wiki 的角落纹理。纹理为本地自绘 `public/assets/hero-halftone.svg`，通过 CSS 遮罩沿用横幅文字色，圆点逐渐缩小，手机上缩小纹理尺寸并保留内容层级；装饰不接收鼠标事件，也不参与布局。“题解分享”使用内联 SVG 摊开书本图标，避免文本符号被浏览器解释为 HTML 后消失。

## 论坛首页图谱交互

欢迎栏的加权图默认展示 `s → v → d → t`，总权重为 9。鼠标悬停节点可临时预览路径；点击或触摸点选节点后，所选路径会保留，离开图谱或滚动页面不会清除选择。键盘用户可用 Tab 切换节点，Enter 或空格选中，Esc 恢复默认路径。节点提供可见焦点和路径、权重说明，点选结果通过状态区向屏幕阅读器播报；系统启用“减少动态效果”时仍可选取路径。

修改图谱时，应验证全部 12 个节点的鼠标点击、触摸点选、键盘选择与最短路径权重；同时检查悬停离开后恢复已选路径、空格不滚动页面、Esc 复位，以及窄屏和减少动态效果下的操作。

## 自助调色

所有使用共享 `app.js` 的页面均提供“自助调色”入口。基础颜色为主色、页面背景、卡片背景和强调色；高级设置可覆盖正文、次要文字、边框、链接、选中项文字及横幅背景。衍生状态和按钮前景自动计算。可选择工业黄、清绿、白灰、暖黄、柔粉五个预设作为起点，也可继续完全自定义。预设仅替换正在编辑模式的草稿；另一模式、已保存主题和命名方案库保持不变。“恢复打开前的配色”可恢复当前模式，取消则恢复整个主题。

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

CF 选题验收应覆盖成员指纹、未绑定 / 过期等就绪状态、近期与历史人数、两种查重口径、题目核实与 202 任务、权限 / CSRF、分页失败 / 中断、verdict 更新、换绑并发与持久化任务恢复。还应检查维护修复后的 AC 重判、组刷新使用游标及失败不推进、并发题库缓存与重启后的 TTL、异常输入 JSON 400，以及既有入口与新请求共用实际节流。比赛请求应使用真实适配器检查最终 HTTP 参数，覆盖普通比赛匿名请求、配置密钥后的普通比赛、Gym 签名和权限失败；历史分页需检查可选 `contestId`、整页不可定位记录、增量时间边界及异常题号。跨入口联调应同时执行成员 A 选题同步、成员 B 的 Bot 挑战 / 训练完成及 A 换绑，并验证取消分页时释放写锁；另需检查旧触发器重复升级、Web 换绑 / Bot 解绑后的个人学习资料完整保留。新账号空历史完成后不能残留旧 AC / attempt，保留的笔记和复习记录不能造成查重排除。浏览器验收应使用独立的合成数据库和模拟 CF 适配器，检查筛选、证据分页、复制、范围变化时旧结果失效、手机布局及键盘操作；演示脚本和数据库不放进仓库。
