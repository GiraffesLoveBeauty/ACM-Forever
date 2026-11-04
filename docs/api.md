# ACM-Forever API 调用指南

本文面向 Web、机器人和其他需要读取 ACM-Forever 数据的程序调用者。代码实现是当前行为的最终依据；接口有变化时，应在同一个 PR 中更新本文和自动化测试。

作者修改帖子、驳回后重投、私有文字历史及审核版本参数见 [forum-post-revisions.md（帖子修改与重新投稿接口）](forum-post-revisions.md)。

## 选择接口和认证方式

| 调用方 | 接口前缀 | 认证方式 | 适用范围 |
| --- | --- | --- | --- |
| 浏览器 WebUI | `/api/*` | 登录 Cookie；写请求带 `X-CSRF-Token` | 用户资料、做题看板、训练、论坛、管理功能 |
| 受信任的服务端程序（如梓喵） | `/internal/v1/*` | `Authorization: Bearer <ACM_BOT_API_TOKEN>` | 成员数据、做题记录、排行榜、训练、同步任务等 |
| 公开只读调用方 | 部分 `/api/forum/*`、`/api/community/leaderboard`、`/api/wiki/*` | 无 | 公开论坛内容和公开排行榜 |

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

## 统一后台及保留的业务接口

后台唯一入口为 `/admin.html`，通过 `section` 选择 `accounts`（默认）、`members`、`training`、`problems`、`cf-practice`、`contests`、`tasks`、`moderation`、`settings`。CF 使用 `tab=recent/check`，审核使用 `tab=posts/reports`，成员详情使用 `qq_id`。浏览器刷新、前进后退和登录 / 强制改密均保留模块参数；原管理页地址由服务端转入对应模块，共用的训练 / 题库 / 赛事路径则按 Web 角色分别进入后台或成员前台。

| 方法与路径 | 权限 / 契约 |
| --- | --- |
| `GET /api/admin/members` | admin/root；`search` 搜 QQ、昵称、身份、学校和 OJ 账号；`page` 默认 1，`page_size` 默认 20、上限 100；返回 `items/total/page/page_size`，含正确的 Web `role` 与 `is_active` |
| `GET /api/member/<qq_id>`、`PUT /api/user` | admin/root；详情、资料与绑定编辑，Web 角色只读 |
| `/api/admin/web-accounts/*` | admin/root；Web 账号管理，角色授予仍要求 root，与 QQBot 名单独立 |
| `GET/PUT /api/admins` | 查询 QQBot Root / 管理员配置；仅 Web root 可写，不修改 `web_accounts.role` |
| `GET/PUT /api/ui/preferences` | admin/root；只返回 / 更新 `font_scale`，旧导航隐藏、排序、复习配置不再参与页面生成 |
| `GET /api/problems`、`GET /api/me/problems` | 管理员可附 `owner_qq_id`，成员接口始终使用会话 QQ；支持 `platform/tag/state=favorite/page/page_size`；题目按平台和 ID 去重，优先目录元数据；分页返回 `items/total/returned/page/page_size`，默认 500、上限 500；不返回笔记 |
| `PUT /api/problems/<platform>/<problem_id>/state`、`PUT /api/me/problems/<platform>/<problem_id>/state` | 正文 `is_favorite` 为必填布尔，管理员另传 `owner_qq_id`；只更新收藏与时间，不覆盖历史状态 / 笔记；提交 `note_md` 返回 410 |
| `GET /api/contest/reviews`、`GET /api/me/contest/reviews` | 管理接口传 `owner_qq_id/contest_id`，本人接口仅 `contest_id`；返回比赛题目、verdict、rating、status，不暴露自由笔记 |
| `PUT /api/contest/reviews`、`PUT /api/me/contest/reviews` | 正文 `contest_id/problem_id` 必填，管理接口另传 `owner_qq_id`；`status/verdict/rating` 至少一个，只更新提供的字段；省略字段及历史 `note_md` 原值保留 |
| `/api/challenge/*`、`/api/me/challenge/*`、`/api/me/training/*` | 保留原训练推荐、挑战历史和统计；`/me/` 对 member / admin / root 均锁定会话本人，管理接口仅允许管理员与 Root |
| `GET /api/tasks`、`POST /api/tasks/<id>/cancel` | admin/root；同步任务与原始结果，刷新 / 取消保留 |

赛事状态统一为 `todo/unsolved/queued/solved/reviewed/ignored`，其中 `reviewed` 可正常保存，`queued` 仅表示待补题状态，不创建复习或计划队列。`rating` 接受整数或 null。任何赛事 `note_md` 写请求均返回 410。所有写请求继续执行 CSRF 校验，模块路由不是权限边界。

## 普通成员训练闭环

个人入口为 `/home.html`、`/my-problems.html` 和 `/problem.html`。主导航和个人中心的“题库”对 member / admin / root 均进入独立 `/my-problems.html`，可浏览全站目录、查看本人已 AC 及收藏；不提供成员 QQ 选择，收藏归属取当前会话。“查看全部已 AC”指向 `/my-problems.html?scope=solved`，仅展示会话本人的 AC；此地址需要登录，刷新、直链、登录及首次改密保留范围、筛选和页码。旧 `/problem-bank.html` 仍供普通成员使用，admin / root 访问时进入统一后台题库。

认证初始化失败进入 `/auth-unavailable.html?next=...`。恢复页跳过自动认证初始化，首次请求超时（15 秒）后即可展示反馈，不会自行发起第二次认证；直接打开恢复页也不查询认证。用户点击“重试原页面”才重新请求并恢复原目标。普通成员访问后台，服务端直链返回 403，客户端导航提供无权限页面。

### 本人 AC 与站内题面

`GET /api/me/problems?scope=solved` 从会话读取 QQ，客户端的 `qq_id/owner_qq_id` 不改变归属。以平台和题号去重，返回 `ac_at`（Unix 秒），按最近 AC 时间倒序，再按平台、题号稳定排序。`platform/tag/state=favorite/page/page_size` 与总数使用相同条件；`tag` 同时匹配题名、题号和标签。本人范围默认每页 20、上限 100，默认全站目录仍为 500、上限 500。返回 `items/total/returned/page/page_size`；无效 `scope` 或非整数分页参数返回 400。

`GET /api/me/problems/tracker` 为个人题库的比赛进度矩阵提供数据，member / admin / root 均只读取会话本人，客户端身份参数不改变归属。支持 `platform`（空、`codeforces`、`atcoder`）、`tag`（比赛 ID / 题号 / 题名 / 标签）、`scope=all|solved`、`state=favorite`、`page` 和 `page_size`（默认 20、上限 50）。无效参数返回 400；未登录或未完成首次改密沿用本人接口权限。

返回 `items/total/page/page_size`，`total` 为比赛数量。每个比赛含 `platform/contest_id/contest_name/start_time/total_count/solved_count/attempted_count/problems`；题目含 `platform/problem_id/problem_index/problem_name/problem_rating/status/ac_at/last_submit_at/is_favorite`。`status` 为 `solved`（已 AC）、`attempted`（有提交记录且未 AC）、`unseen`（未记录），时间为 Unix 秒。`start_time` 为真实比赛开始时间，未收录时为 null；默认按开始时间倒序，未知时间在后，同时间以平台和自然比赛 ID 稳定排序，再进行分页。AC 证据优先于之后的失败提交；收藏和提交状态只关联本人。按自然题序排列 D1 / D2 等题目，筛选先选择比赛，再返回该场全部已入库题目，分页不会切开比赛。前端每页完整展开 20 场，使用页面纵向滚动。仅使用本地目录、比赛缓存和提交数据，不调用 OJ 或触发采集；未记录不代表原站没有提交，目录和尝试记录均可能尚未同步完整。

前端 `/my-problems.html?view=tracker` 切换比赛进度；默认列表省略 `view`。前端题库的平台筛选默认 Codeforces，不提供“全部平台”；未指定或无效平台回落为 `codeforces`，清除筛选同样恢复该默认值。接口自身仍支持空平台供兼容调用。站内题面返回白名单保留 `view=tracker` 和已有范围、筛选、页码，排除身份参数。

个人中心的最近 AC 和个人题库均打开站内题面。`from` 仅接受 `/home.html`、携带允许筛选参数的 `/problem-bank.html` 或 `/my-problems.html`；外部网址、管理地址和身份参数会被排除，返回时保留实际个人入口。个人列表与收藏对所有角色均使用 `/api/me/problems`，归属只取会话本人；成员详情及 PDF 读取复用 `/api/me/problems/<platform>/<problem_id>` 和后缀 `/statement.pdf`，admin / root 的详情沿用原管理读取接口，两者均不会触发采集。

比赛进度中的题目若仅有会话本人的提交尝试、尚无题库目录，两个题目详情入口均回退读取本人的 `submission_attempts`，返回题号、所属比赛和规范的原题链接，`content_available=false`、`samples=[]`，沿用“题面尚未采集”提示。此回退不读取其他账号的尝试，不返回源码或提交详情，也不联网或新增目录；无本人的有效记录时仍返回 404。已有采集题面和目录元数据优先。

CF 详情及 PDF 接口在读取时统一解析 `100A` / `cf_100A` 等前缀和大小写别名，包括旧目录、推荐和 AC 元数据；题号仍保留在原记录中，详情返回实际命中的题号。同一 CF 题号存在多条目录记录时，优先已保存的题面，可用性相同时优先精确题号；PDF 读取优先已有 PDF，继续支持 Range。AtCoder 题号保持精确匹配。

### 绑定与同步接口

所有接口均要求完成首次改密的 Web 会话，写入必须带 `X-CSRF-Token`，操作对象仅为会话本人。`cf` 与 `codeforces` 在服务端统一为 `codeforces`。

| 接口 | 请求 / 返回 |
| --- | --- |
| `GET /api/me/profile` | 新增 `bindings` 数组，每个平台包含 `platform/label/account/binding_status/self_service/sync_status/last_success_at/message/verification`；`verification` 是本人仍有效的验证信息或 null |
| `POST /api/me/bindings/<platform>/verification` | JSON `account`；返回 `verification_id/account/code/expires_at/instructions`。验证码 10 分钟有效，重新申请替换旧验证 |
| `POST /api/me/bindings/<platform>/confirm` | JSON `verification_id`；改绑还须提交 `password`、`confirmed:true`、`current_account`；服务端重新读取公开资料核验，成功消费验证并提交绑定 |
| `DELETE /api/me/bindings/<platform>` | JSON `password`、`confirmed:true`、`current_account`；确认当前 Web 密码及目标账号后解绑 |
| `POST /api/me/bindings/<platform>/sync` | 无需指定成员；仅调度本人已绑定的平台；同步创建成功返回 202 和 `task_id` |

Web 归属验证当前实现 Codeforces：账号存在性使用已有验证器，归属只检查目标 `user.info` 的 `firstName/lastName/organization`。用户将验证码写入公开资料，不提供 OJ 密码。其他平台 `self_service=false`，保留查看、同步、密码确认后的解绑和管理员代操作；真实平台归属验证联测前不开放自助绑定 / 改绑。此次自动测试与浏览器测试使用模拟 CF 资料，真实账号的正向归属验证仍待联测。

管理员导入且尚未完成本人核验的 Codeforces 绑定，允许向 `verification` 申请当前 handle（忽略大小写）的验证码；来源记录必须匹配当前账号与绑定版本且 `owner_verified_at=null`。确认接口仍要求当前 Web 密码、明确确认和服务端公开资料归属验证。成功后原子更新来源为 `member_verified`，保留原账号、绑定版本、AC、提交证据及活动挑战；仍沿用确认后的同步调度。已核验、无来源记录或来源与当前绑定不匹配时，重复申请当前 handle 返回 `409 already_bound`。

`binding_status` 为 `unbound/pending/bound`，同步为 `never/queued/running/success/failed`。`last_success_at` 为 Unix 秒，0 代表没有成功记录。`verification` 含 `account/verification_id/code/expires_at`，不能将该资料发给其他成员。服务重启后丢失的运行中任务显示失败并可重试；旧账号的任务不会使新绑定显示同步中。绑定提交与同步调度分别反馈：排队失败时响应仍表明绑定成功，`sync_status=failed`，刷新后仍能看到失败状态。

限频按成员、平台、动作持久保存：申请验证码间隔 30 秒，确认与解绑间隔 3 秒，同步间隔 60 秒，每个动作最多 15 次 / 15 分钟；上游核验并发最多 4。常见错误为 `confirmation_required`（400）、`invalid_password`（403）、`ownership_unverified`（400）、`verification_expired/verification_changed/binding_changed/account_occupied`（409）、`rate_limited`（429）、`upstream_unavailable/verification_unavailable`（503）。仅浏览器提交“已验证”不会完成绑定。

成功解绑 / 改绑在同一事务清理该成员该平台的 AC、提交证据、同步状态并结束活动挑战；收藏、历史笔记、复习与计划存档保留。每个平台使用持久绑定版本拦截旧同步批次，包括解绑后重绑同名账号的情况。

管理员 `PUT /api/user`、`POST /api/register` 改动 OJ 绑定时，须附 `confirm_bindings:true`、`expected_bindings`（按字段名，如 `cf_handle`）和 `binding_versions`（按平台名，如 `codeforces`）。版本来自成员详情中的 `cf_binding_version/luogu_binding_version/nowcoder_binding_version/atcoder_binding_version/cjlu_binding_version`；新成员的预期账号为空、版本为 0。资料编辑省略的绑定字段不会被清空。成功与确认失败均记录操作者、目标、平台、动作、结果和时间，不保存提交的密码。

迁移、备份与验收边界见 [issue-52-member-training.md（普通成员训练闭环）](issue-52-member-training.md)。

## 管理员采集新题目

### 网页操作

题库管理顶部的 **服务端数据库 → 初始化数据库** 会补齐 SQLite 表结构，保留已有账号、设置、题目及样例；页面显示各平台目录数量、已采集数量、失败数量和样例组数。服务启动仍自动初始化，也可使用已有 `python -m api.init_db` 命令。

题库管理页的 **题库记录** 可视化浏览 `crawler_problems` 中的目录数据、采集状态、样例数和更新时间，并按平台、题面状态及题号 / 题名 / 比赛 ID 搜索。对应的 `GET /api/admin/database/problems` 仅限 Web 管理员 / Root，支持 `q`、`platform`、`status`、`page` 和 `page_size`；题面正文通过下方题目详情接口读取。

管理页按 **服务端数据库 → 拉取题目 → 题库记录** 排列；浏览和收藏题目的独立题库通过主导航进入，不再混排在管理页。初始化、目录导入和采集批次完成后刷新题库记录，并保留记录表当前筛选和页码。

题库列表右侧的 **打开题目** 进入 `/problem.html?platform=codeforces&problem_id=cf_1843A` 等站内详情页，读取服务端已保存的题面与样例。管理员使用 `GET /api/problems/<platform>/<problem_id>`，普通成员使用 `GET /api/me/problems/<platform>/<problem_id>`；都要求登录且完成首次改密。返回题名、难度、标签、原题链接 `problem_url`、`statement_html/statement_text`、题面语言、`samples`、采集时间、最近采集状态和 `content_available`。读取不触发爬虫；题目不存在返回 404，只收录目录时返回 200 且 `content_available=false`，提示等待采集或管理员重试。更新失败但仍有旧题面时继续展示已保存内容。详情页的“查看原题”按钮在新标签页打开数据库中记录的原题链接，正文尚未采集时也可使用。

详情页清理外部 HTML，保留样例空格和换行并提供复制按钮；公式使用本地 KaTeX 0.19.0 输出 MathML（[配置说明](https://katex.org/docs/autorender)）。题面图片目前仍从 AtCoder / Codeforces 的 HTTPS 域名加载，尚未存入本地数据库；其它来源的图片显示占位文字。仅详情页允许这些图片域名，其它页面继续使用原有内容安全策略。

CF 原题未提供样例时（如 171E 的空样例区），采集成功并返回 `samples=[]`；存在一侧输入或输出、缺少 `pre` 等损坏样例仍报错。已有样例的 HTML 刷新结果意外变空时，继续保留旧题面和样例。

AtCoder 仅输出题在输入章节明确无输入时返回 `samples[].input=""`。原站明确省略巨大输出时返回 `output=null` 及 `output_note`（官方说明），网页显示“输出说明”且不提供复制输出；调用方不能将该说明或 null 当作期望答案。APG 课程及错误程序演示保留在正文，不作为同一道题的正式样例。叙述重复、历史错编号的处理边界见[采集说明](crawler-samples.md#样例直接保存在题目中)。原站 404 和空题面仍记录失败，便于后续重试。

旧 ICPC 输出标题和严格配对的多组无编号样例也可采集。源编号从 0 开始时，`samples[].index` 规范为正数，并由 `source_index` 保存原编号。附件型样例可返回 `input=null` / `output=null`、对应的 `input_note/output_note` 及 `attachments: [{url, name}]`；附件仅保留官方 `https://img.atcoder.jp/` ZIP 链接，未展开为文本。未提供输出的官方补充输入同样通过 `output_note` 说明。null 不表示空字符串答案。首选语言排版损坏但页面内另一语言可严格解析时，整体回退并如实记录实际 `statement_language`；`requested_language` 仍保存原请求。

PDF 题面（如 497D）将原始字节保存到 SQLite 的 `crawler_problems.statement_pdf`，详情返回 `statement_format="pdf"`、`content_available=true`；JSON 不包含二进制。HTML / 纯文本题面分别返回 `statement_format="html"` / `"text"`，未采集时为 null。详情页的 **打开已采集 PDF** 使用本站 `GET /api/problems/<platform>/<problem_id>/statement.pdf`，成员使用 `/api/me/problems/<platform>/<problem_id>/statement.pdf`；权限与详情接口相同，支持字节范围读取，未保存 PDF 返回 404。PDF 中的图示、公式和样例按原文件保留，暂不拆分为结构化 `samples`，不计入样例组数。PDF 校验文件头、结束标记和 20 MiB 上限；不完整文件采集失败且保留旧内容。

旧数据库在启动或初始化时自动补充可空的 `statement_pdf` 列，保留已有题目。已成功保存的 PDF 与 HTML 一样计入已采集统计，并在默认重复采集时跳过。

PDF 在题目详情页内通过本地 PDF.js 绘制，支持翻页、缩放和适应宽度，同时保留单独打开按钮。渲染器、Worker、字体和字符映射资源均随前端构建部署；PDF 仍通过本站鉴权接口读取，不放宽页面的禁止嵌入策略。

管理员或 Root 登录后，在 **管理后台 → 题库管理 → 拉取题目** 中选择 AtCoder / Codeforces，填写比赛 ID 和本次最多拉取题数（1–100），点击 **开始拉取**。可以指定题号（逗号或空格分隔）；留空时按比赛题序处理。AtCoder 可选英文或日文，Codeforces 使用英文且暂不支持 Gym。

将 **拉取范围** 切换为 **该平台全部题目** 时，不需要比赛 ID 或题号，题数输入变为 **每批处理题数**（1–100，默认 100）。点击 **拉取该平台全部题目** 后，服务器先分批导入整个公开目录，再自动处理全部待采题目；批次大小不是总数量上限。页面显示目录导入进度、题面进度与批次，目录导入及批次完成后刷新题库与数据库统计。

默认跳过成功采集的题目；勾选 **重新拉取已有题目** 时更新已有题面与样例。页面自动显示任务进度、成功 / 失败数量和失败原因，完成后刷新题库列表。题数只是本次上限，实际数量受比赛题目数及已采集数量影响。

拉取过程中不能重复提交。离开页面后后台任务继续执行，返回题库管理时恢复进行中的任务。也可在 **同步任务** 中查看或取消；任务取消后已入库题目会保留。

### 后端接口

`GET /api/admin/database` 返回 `initialized`、`missing_tables` 和 `platforms` 统计数组（`platform/total/collected/failed/samples`）。`POST /api/admin/database/init` 使用服务器配置的数据库执行初始化，接受空请求或 `{}`，不接受文件路径或重置参数，返回 `success/message` 及相同统计。两者要求管理员或 Root 会话；初始化还须携带 CSRF。初始化可以重复执行，保留已有数据。

`POST /api/admin/problems/sync` 让服务器直接抓取公开 AtCoder 或 Codeforces 题目，并写入服务端 `ACM_DATABASE_PATH` 指定的 SQLite。使用 Web `admin/root` 登录 Cookie，必须携带 `X-CSRF-Token`。未登录返回 401，普通成员或缺少 CSRF 返回 403，需要首次改密时返回 428。

请求示例：

```json
{
  "platform": "atcoder",
  "contest_id": "abc370",
  "problem_ids": ["abc370_a", "abc370_b"],
  "limit": 20,
  "language": "en",
  "refresh": false
}
```

| 参数 | 规则 |
| --- | --- |
| `platform` | `atcoder`（默认）或 `codeforces` |
| `scope` | `contest`（默认，单场比赛）或 `platform`（该平台全部题目） |
| `contest_id` | `scope=contest` 必填；AtCoder 比赛 ID 为字符串，如 `abc370`，最长 100 个字符；CF 为 1–99999 的普通公开比赛 ID，可传整数或数字字符串，当前不支持 Gym；全平台模式不传此字段 |
| `problem_ids` | 可省略，最多 100 个题号；空数组表示该比赛全部题目，重复题号去重；题号必须属于指定比赛；CF 接受 `1843A` 或 `cf_1843A`，统一保存为 `cf_1843A`，与既有提交记录一致 |
| `limit` | 仅用于单场比赛，本次最多尝试的题面数量，整数 1–100，默认 20；先跳过成功题目，再按原站题序取前若干道 |
| `batch_size` | 仅用于全平台采集，每批处理题数，整数 1–100，默认 100；自动处理所有批次，不限制总题数 |
| `language` | AtCoder 为 `en`（默认）或 `ja`，缺失英文时回退到日文；CF 当前只支持 `en`；单条记录只保存一种语言 |
| `refresh` | 布尔，默认 false；true 时重新采集已保存的题目 |

只采集指定比赛的新题目时，传 `{"contest_id":"abc370"}` 即可。重复调用会继续处理尚未成功的题目；同一题的重复采集更新已有记录。参数类型、未知参数或不支持的平台返回 JSON 400 `invalid_request`。比赛及题号是否公开存在在异步抓取时核实；核实失败记录在任务结果中，不写入无效题目。这个接口不接受题面 JSON 或任意抓取 URL。

CF 请求示例：

```json
{"platform":"codeforces","contest_id":1843,"problem_ids":["1843A","1843B"],"limit":10}
```

CF 元数据来自匿名 `contest.standings` 的题目列表（仅传 `contestId`），正文与样例来自原站题目页面。页面访问受限、HTTP 错误或解析失败时报告失败，不使用空白题面代替实际内容。

全平台请求示例：

```json
{"platform":"atcoder","scope":"platform","batch_size":100,"language":"en","refresh":false}
```

将 `platform` 改为 `codeforces` 可拉取 CF 整个平台。全平台模式不接受 `contest_id/problem_ids/limit`。AtCoder 目录来自 [AtCoder Problems 题目数据集](https://github.com/kenkoooo/AtCoderProblems/blob/master/doc/api.md)，CF 目录来自官方 [`problemset.problems`](https://codeforces.com/apiHelp/methods#problemset.problems)。范围为这些公开目录中的可访问题目，CF 不包含 Gym、私有比赛或自定义 problemset；目录索引可能有延迟。题面与样例仍取自原站。目录去重后写入 `crawler_problems` 与 `recommendations`，未下载题面时为 `last_fetch_status=never`，题库可先展示目录；正文尚未采集时，站内详情页显示等待提示。

全量采集逐题限速，可能持续数小时。每道成功题目立即提交，失败题目保留元数据并记录 `last_error`；个别失败继续处理后续题目。取消或服务重启后再次以 `refresh=false` 运行，跳过成功且语言相同的题目，重新处理失败及尚未采集的题目。`refresh=true` 会重新处理全平台所有题目。单场比赛仍按 `limit` 截取，全平台自动处理全部批次。

CF 历史比赛中的纯数字题序也包含在目录中，例如比赛 921 的题序 `01` 保存为 `cf_92101`，指定题号时可使用 `92101/cf_92101`。

成功提交返回 202：

```json
{
  "success": true,
  "status": "queued",
  "task": {"id": "任务ID", "merged": false}
}
```

同一个 API 进程同时运行一个题目采集任务，相同参数的进行中请求合并为同一任务（`merged=true`）；其他采集请求返回 409 `problem_sync_busy`，可等待或取消当前任务。AtCoder 题目请求串行执行，前一次结束后至少等待 1.5 秒；CF 元数据与题面请求共用现有 CF 请求节流，至少间隔 2.1 秒。单次请求超时为 30 秒。

登录方式沿用上文的 `session` 与 `csrf_token`，触发和查询示例：

```python
response = session.post(
    f"{base_url}/api/admin/problems/sync",
    headers={"X-CSRF-Token": csrf_token},
    json={"contest_id": "abc370", "problem_ids": ["abc370_a"]},
    timeout=15,
)
response.raise_for_status()
task_id = response.json()["task"]["id"]

response = session.get(f"{base_url}/api/tasks", timeout=15)
response.raise_for_status()
task = next(item for item in response.json() if item["id"] == task_id)
print(task["status"], task["progress"], task["result"])
```

`GET /api/tasks` 返回任务数组。题目任务 `kind=题目采集`，`progress` 含 `done/total` 和正在采集的 `problem_id`，`result` 含比赛 ID、发现数量、筛选数量、跳过数量、本次尝试数量、剩余待采数量、成功/失败数量、样例组数及错误清单。可每 2–3 秒查询，直到 `status` 为 `completed/partial/failed/cancelled`。个别题目失败时继续采集，成功和失败并存时为 `partial`；比赛列表获取失败等整体错误保存为 `result.error`。202 仅表示接受任务，是否成功以最终状态和计数为准。

`result.scope=platform` 表示全平台任务；`metadata_count` 是已导入目录题数，`batch_count/completed_batches` 是题面总批次 / 已完成批次。`progress.phase` 为 `catalog/metadata/statements`，目录阶段有 `metadata_done/metadata_total`，题面阶段有当前 `batch`。全平台的 `remaining_count` 表示本任务尚未尝试的题数，失败题数单独统计。任务错误列表最多显示前 100 条，超出时 `failure_details_truncated=true`；完整逐题错误保存在数据库对应行中。

取消仍使用 `POST /api/tasks/<任务ID>/cancel`，要求同样的管理员 Cookie 与 CSRF。任务记录保存在进程内，服务重启后清空；已入库的数据保留，再次提交时可跳过成功题目。

成功的题面 HTML（包含样例章节）、纯文本及 `samples` JSON 数组存于 `crawler_problems` 的同一行，没有独立样例表。样例保留输入输出的空格与换行，CF 的逐行 div 和旧版 br 排版会还原为换行。AtCoder 空白处理详见 [采集说明](crawler-samples.md#样例直接保存在题目中)。同时原子更新现有 `recommendations`，使 `GET /api/problems` 和成员题库列表能够展示新题。AtCoder 官方列表不提供估算难度和算法标签，新题的这些信息为空，已有数据在刷新时保留；CF 保存元数据中的 Rating 与 tags，缺失 Rating 为 null。下载、解析或数据库写入失败时保留已有题面与样例，并在已有题目行中记录最近失败。

服务启动会自动建表；也可先在部署目录运行 `python3 -m api.init_db --database /home/WYJ/acm-forever-data/acm_forever.db`，详见 [服务端初始化说明](../feat/api/README.md#单独初始化数据库与题目采集)。

## 已下线的 Web 功能

待复习 / 待复盘、提交时间线、笔记与计划工作区及其 Web 专属接口已下线。旧页面 `reviews.html/submissions.html/workspace.html` 显示“功能已下线”，可返回个人中心或管理中心。以下路由保留原身份及 CSRF 守卫，已授权调用统一返回 `410`、`code=feature_retired`，不读写历史学习数据：

| 功能 | 管理员路径 | 成员路径 |
| --- | --- | --- |
| 工作区 | `/api/workspace/items`、`/api/workspace/items/<id>` | `/api/me/workspace/items`、`/api/me/workspace/items/<id>` |
| 复习队列 / 反馈 | `/api/review/queue`、`/api/review/feedback` | `/api/me/reviews`、`/api/me/reviews/feedback` |
| 复盘草稿 | `/api/reviews/drafts` | `/api/me/reviews/drafts` |
| 计划 | `/api/study-plan` | `/api/me/study-plan` |
| 提交时间线 / 分析 | `/api/submissions/attempts`、`/api/submissions/analytics` | `/api/me/submissions/attempts`、`/api/me/submissions/analytics` |
| 成员详情中的 Web 权限修改 | `/api/member/<qq_id>/permissions`，改用成员账号 PATCH 接口 | 无 |

`workspace_items/user_problem_state/review_states/study_plan_items/contest_problem_reviews` 表及历史记录保留存档，不删除表。提交同步继续写入 `submissions/submission_attempts`，内部 `/internal/v1/*` 的提交读写、同步、统计、训练与机器人接口保持可用；CF 近期、证据、候选查重继续使用完整提交历史。训练弱项的 `/api/training/weak-tags`、`/api/me/reviews/weak-tags` 虽含旧命名仍保留，作为训练统计保留，只读取已有提交和归档的错误统计，不提供复习队列或反馈操作。同步和赛事状态写入解除学习队列联动。

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
| `POST /api/forum/images` | Web 登录 + CSRF | 上传帖子图片；`multipart/form-data` 字段 `image`，接受静态 PNG/JPEG/WebP，最大 5 MB |
| `GET /api/forum/images/<id>` | 按引用状态授权 | 已发布帖子中的图片公开；其余仅上传者、引用内容的作者及已提交帖子的审核员可读 |
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

### 回复通知与投稿进度

登录成员可通过页头“通知”进入 `/notifications.html`。未读数在页面可见时每 30 秒更新，切回页面或修改已读状态时也会刷新。通知保存在数据库中，退出或刷新不会丢失。评论通知发送给话题作者；回复还会通知被回复评论的作者，同一条评论对同一收件人仅通知一次，不发送评论者给自己的通知。审核通过或退回会通知投稿人，管理员退回时须填写原因。

| 接口 | 权限 | 行为 |
| --- | --- | --- |
| `GET /api/me/notifications/count` | 成员登录 | 返回本人 `unread_count` |
| `GET /api/me/notifications` | 成员登录 | 返回 `rows/total/page/page_size/unread_count/latest_id`；支持 `unread=1`、`page`、`page_size`（默认 20、上限 50） |
| `POST /api/me/notifications/<id>/read` | 成员登录 + CSRF | 将本人的通知标为已读，可重复调用；他人通知返回 404 |
| `POST /api/me/notifications/read-all` | 成员登录 + CSRF | JSON 传列表返回的整数 `through_id: latest_id`，只标记该快照及之前的本人通知，保留此后到达的新通知 |
| `GET /api/forum/mine/posts/<id>` | 成员登录 | 仅作者可读的投稿原文、封面、状态、提交时间、`reviewed_at` 与 `review_reason`；他人（含管理员）访问此个人接口返回 404 |
| `POST /api/forum/moderation/posts/<id>` | 管理员 + CSRF | `decision` 为 `publish/reject`；退回时 `reason` 必须为非空字符串，最多 1000 字符；仅处理待审核帖子 |

通知不返回评论正文或账号 QQ，`target_url` 由服务器按当前可见性生成；原话题不可访问时不提供跳转，已隐藏或移除的回复不再提供对应回复链接。回复链接带 `comment_id` 与 `#comment-<id>`；公开详情支持该参数，在默认前 500 条评论之外最多补充目标评论及其父评论，仍校验同一话题和公开状态。已读不会授予原内容访问权限。

发帖成功后进入 `/my-post.html?id=<id>` 查看实际状态（等待审核 / 审核通过 / 审核未通过 / 已删除），个人中心“我的话题”也提供入口和退回原因；未公开原文仅作者可在个人接口查看，公开帖子接口不放宽。审核通知和状态修改、回复通知和评论写入分别处于同一事务，失败整体回滚。

数据库初始化增量添加 `forum_posts.review_reason` 和 `forum_notifications`，可重复执行；保留原帖子和已有图片，不补发历史通知。旧的退回记录未保存原因时，界面明确提示此前未记录原因。回退代码不会删除新增表和字段；恢复生产数据仍应使用发布前的数据库及上传目录备份。

### 帖子封面与正文图片

上传接口返回 `201` 和 `{id, url, width, height, size_bytes}`。在草稿创建、保存或直接发帖的 JSON 中传入 `cover_image_id` 设置封面，传 `null` 移除封面；正文使用 `![说明](/api/forum/images/<id>)` 插入图片。列表、详情及审核记录返回可空的 `cover_url`，草稿详情同时返回 `cover_image_id`。旧客户端不传封面字段时按无封面保存。

Web 编辑器支持选图、粘贴和拖入，接受最大 20 MB 的原图，上传前自动缩小至最长边 2560 像素并压缩；直接调用上传 API 时文件必须小于等于 5 MB，最长边不超过 10000 像素且不超过 2000 万像素。服务器实际解码并重编码为 WebP，移除原始文件名与 EXIF 元数据，不接受 SVG 或动图。每篇帖子最多引用 30 张图片，每个账号最多存储 1000 张、合计 200 MB。

图片引用与草稿或帖子在同一事务中保存。其他成员的私有图片不能被引用；已公开图片可被其他帖子复用，已有合法引用在原帖删除后仍可用于本人草稿。未提交草稿中的图片不会向管理员开放；提交审核后审核员可查看，发布后访客可查看。图片不使用公开缓存，帖子移除后仅在仍有其他已发布引用时继续公开。移除封面或删除草稿会解除对应引用；删除帖子通过状态隐藏内容及图片。上传文件暂时保留并计入账号限额，当前不自动回收。

删除成员时，图片上传记录的归属自动置空，不再阻塞原有的成员删除流程；其他帖子和草稿的图片引用及访问规则继续生效。没有剩余引用的私有图片仍不可访问，使用相同 QQ 重新创建账号也不会获得旧图片的所有权。已有图片表会在启动时自动迁移，保留图片元数据及引用。

元数据和引用存入 SQLite 的 `forum_images` / `forum_image_links`，文件保存在 `ACM_DATABASE_PATH` 所在目录的 `uploads/forum/`。备份或迁移时须同时保留数据库和上传目录。反向代理须允许至少 6 MB 的请求体（如 Nginx 的 `client_max_body_size 6m`），以容纳 5 MB 图片和 multipart 字段。Markdown 仅展示本站上传接口生成的图片，外链或 data URL 图片会显示替代文字。

## CF 练习赛选题管理员接口

页面入口：管理中心 → CF 练习赛选题（`/admin.html?section=cf-practice`，旧 `/cf-practice.html` 自动转入）。以下接口仅支持 Web `admin/root` 会话，所有 POST 均要求 `X-CSRF-Token`；普通成员返回 403，未登录返回 401，首次改密流程沿用 428。成员身份取 `users.status`，与权限角色分开。

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
| `410` | 专属 Web 功能已下线（`feature_retired`），历史资料保留存档 |
| `429` | 登录请求过于频繁或后台任务队列已满；等待后重试 |
| `503` | 服务或必要配置不可用；稍后重试或联系服务维护者 |

建议为所有请求设置超时，对 `429` 和临时 `5xx` 使用有上限的退避重试；不要对非幂等写操作盲目重试，以免重复创建数据。

## Wiki 知识手册与共享 Markdown

Wiki 使用 `/api/wiki/*` 公开读取当前发布内容，admin/root 使用 `/api/admin/wiki/*` 维护分类、文章和修订；维护写请求沿用 Cookie 与 CSRF。读者不需要绑定 OJ。分类、文章源文、发布指针与历史独立持久化，草稿不会改变公开正文和检索结果。

- `GET /api/wiki/navigation`、`/categories/<id>`、`/pages?category_id=...`、`/search?q=...`：目录与分页检索；默认 20、上限 50。
- `GET /api/wiki/pages/<slug>`、`/revisions`、`/revisions/<id>`：当前正文与可公开历史。
- `GET /api/wiki/pages/<slug>/markdown`：公开源文下载；`revision_id` 选择公开历史。
- `POST /api/markdown/assets`：multipart `file/document_type/document_id`；Wiki 类型仅管理员，论坛草稿仅本人；PNG/JPEG/WebP 实际解码，2MB/4096px。
- `GET /api/markdown/assets/<id>`：按发布引用与文档归属鉴权，私有资源匿名返回 404。
- 论坛公开话题和本人草稿的 `/markdown` 下载调用同一源文导出逻辑。

文章修订写入携带 `version/base_revision_id`；分类写入携带目录版本；409 必须保留输入并核对最新状态。发布和删除携带 `idempotency_key`。所有维护接口和源文下载不进入公共缓存；公开 JSON 支持 ETag（弱标签、多标签与 `*`）。公开目录、分类、文章列表和搜索使用应用级有界字节缓存及数据库版本校验，返回 `Cache-Control: public, max-age=0, must-revalidate` 和 `Server-Timing`；正文及公开历史本轮不缓存响应体。可通过 `ACM_WIKI_CACHE_ENABLED=false` 关闭，数据库恢复后必须重启或清空所有 worker 的缓存。完整请求表、限制、删除预览、恢复与持久化配置见 [Wiki 实现与运维说明](wiki.md)。


## Issue #83：账号注销与生命周期

策略 `closure-v2` 已按最新要求确认（允许同 QQ 新建账号），生产新注销开关 `ACM_ACCOUNT_CLOSURE_ENABLED` 默认关闭。`GET /api/auth/me` 返回 `account_closure_enabled`；在所有实际客户端、旧写入节点和运维措施验收前保持关闭。详细处理清单见 [issue-83-account-closure.md（账号注销与发布验收）](issue-83-account-closure.md)。

| 接口 | 身份与参数 | 结果 |
| --- | --- | --- |
| `GET /api/me/account-closure/preview` | 当前本人，不能指定目标；开关开启 | 策略、epoch、阻断原因、删除/保留计数、request_id 和一次展示的 receipt_token |
| `POST /api/me/account-closure` | 本人有效会话 + CSRF + 当前密码；`Idempotency-Key`=request_id，`X-Closure-Receipt`=秘密 | 同一短事务关闭账号、清私有数据、撤销凭据/绑定并写成功审计；提交成功后才返回 closed、清会话 |
| `GET /api/account-closures/<request_id>` | 仅 `X-Closure-Receipt` 秘密，不需要登录，不接受 QQ | 最小结果：request_id、policy_version、status(pending/closed)、committed_at、cleanup_state；无身份、凭据或资源路径 |
| `GET /api/admin/account-closures/audit?page=1` | 有效 Web root，已完成强制改密 | 每页 50 条脱敏动作、结果码、策略、计数及时间，无明文回执 |

注销 POST JSON：

```json
{"current_password":"原样传入，不 trim","confirm_text":"注销账号","policy_version":"closure-v2","expected_account_epoch":1}
```

请求只允许上述四个字段；`qq_id/owner_qq_id/target_qq_id` 等目标字段拒绝。密码最长 256 字符，不持久化，也不参与幂等指纹。预览秘密本身不能授权关闭。提交前再次在事务内核对凭据、hash、epoch、角色、策略与预览版本；失败回滚。

已提交请求先走秘密认证的只读回放分支，允许旧登录失效后重试，并且不会清除另一个新账号或同 QQ 新代际的会话；已提交的 v1 回执保持原策略版本并可只读回放。不同非密码意图返回 `IDEMPOTENCY_CONFLICT`。未知、错误秘密及过期回执统一 404；回执 24 小时后失效。只关闭新请求开关不会禁用已有结果查询。网络中断或 5xx 应显示“结果待确认”，保留回执查询，不能以 `/auth/me` 未登录推断成功。

| 场景 | HTTP / 结果码 | 调用方处理 |
| --- | --- | --- |
| 开关未启用 | 404 `FEATURE_DISABLED` | 隐藏新注销入口 |
| 账号 closed / 旧 epoch | 409 `ACCOUNT_CLOSED` / `ACCOUNT_CHANGED` | 停止旧代际写入；新建账号须走管理员单个创建入口 |
| 密码错误 / CSRF 不符 | 403 `REAUTH_FAILED` / `CSRF_INVALID` | 清密码输入，重新核对 |
| 角色交接 / 最后 root | 409 `ROLE_HANDOVER_REQUIRED` / `LAST_ROOT_PROTECTED` | 由另一有效 root 完成交接并降为 member |
| 强制改密尚未完成 | 409 `MUST_CHANGE_PASSWORD`（审计读取为 428） | 先完成改密 |
| 旧凭据失效 | 401 `AUTH_REQUIRED` | 通用接口重新登录；注销流程保留回执确认结果 |
| 敏感操作过频 | 429 `RATE_LIMITED` | 遵循 Retry-After；跨连接 HMAC 计数 |
| 存储暂不可用 | 503 `STORAGE_BUSY` / `STORAGE_UNAVAILABLE` | 不宣称成功，用回执确认 |
| Bot DELETE 仍关联 Web 账号 | 409 `WEB_ACCOUNT_PROTECTED` | 不物理删除成员，不作为代注销路径 |

限频窗口 15 分钟：预览每账号 10/IP 60；重新认证每账号 5/IP 20（验证前预留预算，成功尝试也计入）；提交入口每 IP 60；回执每 IP 120。保存 HMAC，不存额外明文 IP。仅信任配置的代理来源。

`GET /api/admin/web-accounts` 中 closed 行保留状态和 closed_at，QQ 脱敏，`qq_id=null`，`display_qq_id` 和不可逆 HMAC `account_key` 用于显示/列表键；原账号的启用与重置操作禁用；同 QQ 可通过单个创建账号建立全新代际。公共帖子/评论增加 `author_closed`，作者显示“已注销用户”、头像 null；Wiki 历史同样派生展示，数据库不可变 author 保留受限引用。

CF 持久 job 成员捕获 epoch，closed 分项不能被晚到成功覆盖；旧快照缺 epoch 必须重排。JSON 任务快照去标识化，候选结果需重新核验，同批其他成员继续执行。所有 Web/受信 Bot 写入仍执行权限、CSRF/服务令牌及最终事务生命周期校验。

同 QQ 新建账号仍使用 `POST /api/admin/web-accounts`，原有管理员权限、角色分配范围与 CSRF 不变；`qq_id`、新 `name` 和 `initial_password` 必填。成功返回 201、`new_generation=true` 和 `must_change_password=true`；未注销的现有 Web 账号返回 409，不覆盖凭据。状态在创建前后变化则返回 409 `ACCOUNT_CHANGED`，事务失败整体回滚。批量发放、普通启用、密码重置、机器人建档及导入不能替代此入口。

预览的 `retention_notice` 返回 `recovery_supported=false`、`reopen_supported=true` 和 `qq_reuse_supported=true`；后两项表示允许同 QQ 创建全新账号，不能恢复旧资料。

新建时 account_epoch 与凭据版本继续递增，OJ 绑定、训练/提交记录、草稿和权限不继承；保留的帖子、评论及 Wiki 仍显示“已注销用户”，新账号不能在“我的帖子”中看到或取得旧内容作者权限，不接收发给旧作者的回复提醒。`GET /api/auth/me` 增加 `account_epoch`，用于前端清理旧代际缓存。回执只读回放同时比较 QQ 和 epoch，不会清掉新会话；旧任务也不能因同 QQ 再次 active 而恢复写回。

## Excel 批量开户与 OJ 资料导入

管理入口 `/admin.html?section=accounts&tab=import`。默认允许新上传及执行，页面顶部提供全站开关。设置持久化到 `settings.account_import_enabled`，对后续请求立即生效并跨进程、服务重启保留。尚未保存页面设置时才采用环境变量 `ACM_ACCOUNT_IMPORT_ENABLED`，其默认值为 `true`；已保存的页面设置优先。全部接口要求具名个人 Web `admin/root`，旧共享 root、普通成员和匿名请求不能使用。写接口沿用 Cookie 与 `X-CSRF-Token`；表格不能指定角色、密码或 QQBot 管理员。

| 方法与路径 | 功能 |
| --- | --- |
| `GET /api/admin/account-imports/capabilities` | 当前有效开关、模板版本、5 MiB/200 行限制、每段 10 人和有效期 |
| `PATCH /api/admin/account-imports/settings` | 仅接受 `{ "enabled": true/false }`，保存全站开关并返回 `{ "enabled": true/false }`；关闭状态下仍可调用以重新开启 |
| `GET /api/admin/account-imports/template` | 下载 `account-import-v1.xlsx` |
| `POST /api/admin/account-imports/preview` | 仅一个 multipart `file`，不接受其他表单字段；201 返回预检摘要 |
| `GET /api/admin/account-imports/{id}` | 无密码摘要、冻结范围、恢复标识及当前处理段 |
| `GET /api/admin/account-imports/{id}/rows` | `status/page/page_size`，默认每页 100、最大 100，逐行结果 |
| `POST /api/admin/account-imports/{id}/commit` | 冻结选择并处理下一段；原始创建响应一次返回凭据 |
| `POST /api/admin/account-imports/{id}/cancel` | 空对象请求，停止未处理行，保留已创建账号 |
| `GET /api/admin/account-imports/{id}/report` | 无密码、强制字符串单元格的 `.xlsx` 报告，到期返回 410 |

开关设置只接受一个真正的 JSON 布尔字段 `enabled`；字符串、数值、空对象和额外字段均返回 `400 invalid_settings`。必须使用具名 Web `admin/root` 及有效 CSRF，普通成员、匿名和旧共享 root 不能修改。关闭后模板下载、新上传及后续提交返回 `503 import_disabled`；正在处理的一段可能完成，已创建账号不撤销。关闭开关后仍可查询、取消及下载未过期报告。默认只有同一账号代际的操作者可访问；root 只读审计其他操作者批次，不能接管提交。凭据版本变化后旧批次只读。

首次确认只接受以下字段：

```json
{
  "preview_version": 1,
  "selected_row_ids": ["opaque-server-row-id"],
  "acknowledge_admin_binding": true,
  "idempotency_key": "random-request-key-at-least-16-chars"
}
```

有新 OJ 写入时必须确认对应关系。所选行只能来自该批次且可执行，已有成员只补开户；错误、占用、已有/停用/注销账号不覆盖。确认时重新检查成员快照、绑定占用和管理员权限。

继续请求只接受：

```json
{
  "preview_version": 1,
  "selection_digest": "server-confirmed-digest",
  "continuation_token": "server-issued-next-token",
  "idempotency_key": "another-random-request-key"
}
```

每段 10 人，写事务外准备强随机密码和 PBKDF2 哈希，逐行业务与台账原子提交。批次内只有一个处理段，SQLite 唯一约束、90 秒租约及随机令牌阻止跨 worker 重复或迟到提交；段有 20 秒启动新行预算。当前段执行完返回 `paused` 并附 `next_chunk_token` 时，可以显式继续。`chunk_status=interrupted` 必须停止自动循环并查询、核对结果。

同幂等键同请求正在处理返回 202；结束后重放返回无密码结果；同键不同内容返回 409。换幂等键不能绕过处理段互斥或冻结范围。刷新恢复不自动继续写入。

创建响应的 `credentials` 只含本请求新创建账号的 `row_id/qq_id/name/temporary_password/expires_at`。`credentials_replayed=false`；摘要、行、报告和重放均不提供明文。服务器不持久保存可恢复密码，也不能保证客户端收到原始响应。响应丢失后先查成功名单，再走已有受控重新发放入口，不能盲目重置。

所有导入响应 `Cache-Control: no-store`，下载设置 Excel MIME、固定文件名和 `nosniff`。表格报告不含密码、公式或外链；凭据文本仅在当前浏览器内存生成。

关键错误码：`named_admin_required/actor_changed`（403）、`batch_not_found`（404）、`idempotency_conflict/batch_busy/selection_changed/account_changed`（409）、`batch_expired/report_expired`（410）、`file_size`（413）、`invalid_workbook/unsafe_content/resource_limit/parse_timeout`（422）、`parse_busy/hash_busy/capacity_limit`（429）、`import_disabled`（503）。字段或选择格式错误返回 400。行级冲突放入对应行结果，不将其他已创建行回滚。

新绑定摘要增加可选 `provenance`：`source=admin_import`、`owner_verified_at=null`、`existence_status=not_checked`；原 `binding_status/self_service/sync_status` 含义不变。现有 CF 本人核验成功后来源为 `member_verified`。不自动同步、不覆盖已有档案或证据。

操作与保留规则见 [admin-account-import.md（Excel 批量开户操作说明）](admin-account-import.md)，设计、实现状态和验证见 [issue-84-account-import.md（Issue #84 实施记录）](issue-84-account-import.md)。
