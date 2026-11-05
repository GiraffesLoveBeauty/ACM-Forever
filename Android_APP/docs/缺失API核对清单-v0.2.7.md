# ACMforever App 缺失 API 核对清单 v0.2.7

核对日期：2026-11-03。核对基准：已获取的远端 `origin/main`，提交 `34e21a9b3c585dc899d061833332413902cd6dd1`（PR #88）。本次只 fetch 读取最新版，没有合并覆盖本地修改，没有上传或部署。

这是**源码与客户端契约核对**，不是正式服务器连通性报告。源码存在不代表服务器已经部署。以下路径均包含 `/api` 前缀；“App 预留路径”表示客户端已有调用约定，不表示后端已实现，也不要求小组必须按该命名另造一套 API。优先扩展现有网页接口。

## 1. 当前确实缺少的业务能力

| 功能 | 最新 main 的缺口 | App 预留调用 / 需要的数据 | 优先复用与小组需决定的事 |
| --- | --- | --- | --- |
| 从论坛、排行榜进入他人主页 | 公开论坛、排行榜没有稳定公开成员 ID | 论坛作者 `author_public_member_id`；排行成员 `public_member_id`，或统一等价字段 | 扩展现有列表/详情返回字段即可。不要把 QQ、管理员成员查询接口或昵称当公开 ID |
| 他人公开资料、各平台累计通过数 | 没有面向普通成员的公开资料查询；本人接口不能代查他人 | `GET /api/mobile/v1/members/{public_id}`；公开 ID、昵称、头像、可选座右铭、各平台累计通过数、合计 | 新增公开只读查询，或扩展现有公开接口。只公开各平台通过题数，不公开逐题记录、QQ 或绑定账号隐私；排行区间统计不能替代终身通过数 |
| 他人发布的话题列表 | 现有公共列表没有作者 ID 过滤；`/forum/mine/posts` 只能查询本人 | `GET /api/mobile/v1/members/{public_id}/posts?page=1&page_size=12`；已发布话题、分页、总数 | 优先给现有 `/api/forum/posts` 增加公开作者 ID 筛选，只返回审核通过的内容 |
| 座右铭读写 / 本人公开资料 | `/api/me/profile` 没有座右铭，PUT 仅修改昵称 | `GET /api/mobile/v1/me/public-profile`、`PUT` 同路径（`motto`）；客户端限制 100 字符 | 可以直接扩展 `/api/me/profile` 与公开资料响应，随后调整 App 路径；无需为了已有本人头像、昵称、过题数重复建接口 |
| 社团题单、截止时间、本人完成进度 | 没有教练下发题单、成员分配和逐题进度接口 | `GET /api/club/sheets`；题单 ID、标题、说明、截止时间、`completed/total`、`items` 内平台/题号/完成状态 | 网页随机训练历史不能替代教练题单。需要 Web 创建/修改/下发能力，以及按已同步 AC 计算本人进度；后台管理留在 Web |
| 按题讨论与标签检索 | 论坛已有发帖、评论、审核，但没有平台＋题号绑定和标签筛选 | `GET /api/club/problem-discussions?platform=...&problem_id=...&q=...&tag=...`、`POST` 同路径；标题、Markdown 正文、标签、所属题目 | 优先扩展现有论坛帖子的数据关联和查询，复用现有评论/审核/举报；不要另建一套评论系统 |
| 私人错题本 | 没有当前 App 的错题条目 CRUD；题目收藏与做题状态不等同于错因笔记 | `GET /api/me/club/mistakes`；`PUT/DELETE` 同路径，题目以平台＋题号定位；错因笔记、标签、时间 | 可评估扩展本人题目状态/收藏。需明确笔记与标签字段、删除语义；仅本人可读写 |
| 补题计划、1/3/7 天复习与今日训练联动 | 当前 main 无 App 的补题计划接口；旧复习队列已下线 | `GET /api/me/club/reviews`、`PUT` 同路径；题目、阶段、到期时间、是否到期；`action=add/reviewed/retry/ignore` | 保留现有赛事复盘接口，扩展其写入逻辑联动计划。需约定幂等生成、重复题目合并、时区和阶段推进；不把已退休路由当可用替代 |
| 每日训练目标与打卡 | 训练汇总只有 AC 活跃日期、连续天数，没有目标达标/打卡记录 | `GET/POST /api/me/club/checkin`；当天 AC、目标、是否达标、是否已打卡、历史 | 优先扩展 `/api/me/training/summary`。以北京时间和服务端已同步 AC 为准；同一天重复提交应幂等 |

本地工作树已有 `club_training.py`、`club_schema.py` 等历史未发布草稿，以及相应 Web 管理草稿，**不在上述 main 提交中**。本轮没有发布它们，不能把本地文件存在当成小组已经完成接口。是否采纳现有草稿由小组评审。

## 2. 兼容约定与后置能力

| 项目 | 核对结果 | 建议 |
| --- | --- | --- |
| 移动能力发现 | main 没有 `GET /api/mobile/v1/capabilities`；App 已按缺失时回退处理 | 可选能力声明，不是业务必须新增的接口。若采用现有客户端协议，返回 `api_version: 1` 与 `features`，目前涉及 `public_member_ids`、`member_profiles`、`member_posts`、`own_public_profile`、`edit_motto`；不采用则调整客户端检测 |
| 北京时间“当日”排行榜 | 现有 `days=1` 是最近 24 小时，没有自然日语义 | 当前 App 跟随网页提供近 7/30/90/365 日与总榜，没有当日入口。若小组恢复当日需求，在现有排行榜增加可选时间边界参数即可 |
| 服务端过滤 0 AC | main 没有处理 `positive_only`；当前 App 已聚合并过滤后重新分页 | 不是页面无 API。后续可给现有接口增加可选过滤及过滤后总数，减少多页请求；不能只过滤当前页导致总页数错误 |
| APK 检查更新 / 发布清单 | main 未找到 Android 版本发布接口；当前精简版已后置应用内更新 | 日后确定版本号、versionCode、包名、最低系统、APK HTTPS 地址、SHA-256、说明与稳定签名。当前不列为在用页面阻塞项 |

## 3. 有路由但已下线，不能当作现成 API

最新 `backend_api.py` 下列成员接口明确返回 HTTP **410**，JSON `code=feature_retired`。这和 404“没有接口”、断网、正常空结果不同：

- `GET /api/me/reviews`、`POST /api/me/reviews/feedback`：旧复习队列/反馈。
- `GET/POST/PATCH/DELETE /api/me/study-plan`：旧学习计划。
- `GET/POST /api/me/workspace/items`、`PATCH/DELETE /api/me/workspace/items/{id}`：旧工作区。
- `GET/POST /api/me/reviews/drafts`：旧复盘草稿。
- `GET /api/me/submissions/attempts`、`GET /api/me/submissions/analytics`：旧尝试/分析接口。

App 新增错题本、补题计划的语义不应靠调用这些接口凑齐。相关功能如要恢复，先让小组决定扩展现有有效接口还是恢复原能力。

## 4. 已有 API，勿重复提需求

| App 功能 | 最新 main 的现有 API |
| --- | --- |
| 登录、会话、密码、退出 | `/api/auth/login`、`/api/auth/me`、`/api/auth/change-password`、`/api/auth/logout` |
| 本人昵称、头像、各平台通过数、最近 AC、绑定摘要 | `GET/PUT /api/me/profile`；`POST/DELETE /api/me/avatar`；现有 `/uploads/avatars/...` 头像文件 |
| 论坛列表、详情、阅读量、分类 | `GET /api/forum/posts`、`GET /api/forum/posts/{id}`、`GET /api/forum/categories`；阅读量字段 `views_count`，详情读取由后端累计 |
| 发帖、评论、点赞、举报 | `/api/forum/posts`、`/api/forum/posts/{id}/comments`、`/like`、`/report` |
| 话题收藏、我的话题收藏 | `POST /api/forum/posts/{id}/bookmark`、`GET /api/forum/mine/bookmarks` |
| 云端多草稿、自动保存、预览素材 | `GET/POST /api/forum/drafts`、`GET/PUT/DELETE /api/forum/drafts/{id}`；预览 Markdown 在本机完成，无须预览 API |
| 投稿进度、修改重投 | `/api/forum/mine/posts`、`/api/forum/mine/posts/{id}`、`POST .../{id}/edit`、`POST /api/forum/drafts/{id}/submit`；遵循 `edit_version` 并发检查 |
| 图片插入、缩略图、正文图片 | `POST /api/forum/images`，multipart 字段 **image**，返回 `url`；`GET /api/forum/images/{id}`、`?variant=thumb`。本轮 App 接入正文插入；不是新增后端 API |
| 多平台组合、区间、排序、分页 | `GET /api/community/leaderboard`，`days/platforms/sort/search/page/page_size` |
| 题库、收藏/状态、比赛进度 | `/api/me/problems`、`/api/me/problems/{platform}/{id}/state`、`/api/me/problems/tracker` |
| PDF 题面 | `GET /api/me/problems/{platform}/{id}/statement.pdf`；翻页/缩放/适宽为客户端能力，个别题目无 PDF 不等于缺路由 |
| 随机训练、历史、训练汇总 | `/api/me/challenge/start`、`/api/me/training/challenges`、`/api/me/challenge/rating`、`/api/me/training/summary`；挑战服务仍依赖部署时 provider 配置 |
| 赛事逐题复盘 | `GET/PUT /api/me/contest/reviews`；不等同于 App 的间隔复习计划 |
| 通知 | `/api/me/notifications`、`/count`、`/{id}/read`、`/read-all` |
| Wiki 导航、检索、阅读、公开历史 | `/api/wiki/navigation`、`/pages`、`/search`、`/pages/{slug}`、`/pages/{slug}/revisions` 与具体历史版本 |
| OJ 核验、解绑、同步 | `/api/me/bindings/{platform}/verification`、`/confirm`、`DELETE /api/me/bindings/{platform}`、`/sync`。按用户决定，App 仅查看绑定并提示去网页端或联系管理员；不是缺 API |

主题库当前从网页主题资源转换后内置在 APK；本机背景图、透明度、模板速查、登录选项、首页最短路径交互与本地提醒无需新 API。当前没有主题云端同步需求。

## 5. 提给小组的决策点

1. 确认公开主页可见字段、稳定公开 ID 与他人话题筛选；逐题记录继续只对本人开放。
2. 确认题单/按题讨论/错题/补题/打卡是否采纳本地草稿，或扩展网页已有接口。
3. 确认旧 410 能力继续下线，避免客户端重新依赖。
4. 确认实际部署版本、可访问 HTTPS 入口及会话/CSRF 配置。后续再用真实服务器验收，源码核对不能替代部署与权限实测。

源码依据：[最新提交](https://github.com/GiraffesLoveBeauty/ACM-Forever/commit/34e21a9b3c585dc899d061833332413902cd6dd1) 中 `feat/api/acm_api/backend_api.py`、`forum_api.py`、`forum_images.py`、`forum_notifications.py`、`wiki_api.py`，以及 `feat/api/app.py` 的 Blueprint 注册；客户端依据为本地 v0.2.7 的 `ApiClient.java`、`ClubActivity.java`、`MainActivity.java`。
