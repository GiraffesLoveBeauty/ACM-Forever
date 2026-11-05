# Android 修改标准与模块关联（v0.2.17）

状态：本轮实现说明，待跨人评审；2026-11-05。以实际代码与测试结果为准。适用工程 `Android_APP/app/`，不改变仓库协作规范。

## 目录与修改入口

Java 路径前缀为 `Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/`。

| 入口 | 职责 | 修改时必须联查 |
| --- | --- | --- |
| `AcmApplication`、`ApiClient`、`SessionVault` | 进程共享会话、CSRF、权限、缓存和加密凭据 | 退出、切账号/服务、Activity 重建、禁止主线程等待网络锁 |
| `MainActivity`、`NavigationStack` | 首页/排名/题库/发帖/个人中心/账号设置及原生详情 | `external_navigation`、详情返回、草稿归属、搜索入口防重 |
| `SearchActivity`、`SearchModules` | 全局搜索、模块顺序、添加/移除、历史记录 | 公开 ID 能力、本人接口范围、缓存及模块独立失败 |
| `MobilePageActivity` | 搜索与便捷管理的页面壳、缓存读取、串行后台操作 | 页面代次、会话代次、槽位绑定、只重试读操作 |
| `AdminQuickActivity`、`AdminApiPolicy` | 手机便捷管理和 API 白名单 | 服务端角色重验证、CSRF、审核版本、敏感内容禁止通用缓存 |
| `ChallengeDifficulty` | 管理员单题训练的难度选项和默认值 | 与 `acm_api/difficulty.py` 的有效值及网页训练默认值一致；切换平台同步难度，空选项不得发送请求 |
| `WebFeaturesActivity` | 通知/投稿进度/比赛进度/Wiki | Wiki 站内练习相对链接进入原生题面，外链 HTTPS 校验 |
| `ClubActivity`、`TrainingReminder` | 题单、讨论、错题、复习、打卡和本地提醒 | 缺失接口保留真实报错，通知授权、返回来源页 |
| `CloudDrafts` 与主页面编辑器 | 云端多草稿和自动保存 | 账号+草稿代次；切换草稿、返回旧页、迟到写入、Markdown 导入归属 |
| `PdfActivity`、`ContentView`、阅读器资源 | PDF、Markdown/公式/代码与图片 | 缩放/翻页/复制、受限媒体地址、缓存边界 |
| `AppAppearance`、`MobileStyle`、`ProfileCover`、`LocalThemes` | 主题、主辅色、全屏背景、模块/控件透明度 | 深浅色、状态栏、原位变色、保存/预览/删除本机主题 |
| `ThemePackage`、`LocalThemes`、`ProfileCover` | `.acmtheme`格式、隔离安装、原图字节与非破坏性裁剪 | [格式规范](android-theme-package-v1.md)；布尔选项、主辅色/透明度、模板浅深配色、原图及裁剪同时往返；文件I/O不在主线程，先校验后登记，导入不覆盖当前外观 |
| `OfficialThemeView`、`theme-renderer/` | 原Vue/CSS/SVG离线主题层，无原生JS桥 | [源文件关联](android-official-theme-adaptation-v0.2.17.md)；原源变化重跑构建工具和指纹检查，禁止用重新描摹替代；原生控件仍使用共享样式 |
| `AppUpdates`、`UpdateManifest`、更新页面与 Provider | 检查、下载、校验及系统安装 | 当前GitHub单源、取消/重建/进程恢复、包名版本签名、更新日志 |
| `tools/create_update_manifest.py`、`tag_release.py` | 同一 APK 的清单和GitHub Release事务 | `.github/workflows/android-release.yml`、签名渠道、不可变目录和 latest |

`AdminActivity`、`BrowserActivity`、`UpdateManager` 与 `assets/admin/` 被当前 Gradle 排除；它们是历史代码。`prototype/` 也是历史浏览器原型，不能通过修改这些文件来声称 Android 已实现。App 不直接访问数据库，不能内置 `/internal/v1/*` 的 Bot Token。

## 搜索接口矩阵

默认顺序为 **用户 → 论坛 → Wiki → 题目**。顺序、启用模块和最近十条记录仅保存在本机，键为 `global_search_modules`、`search_history`、`record_search`。空模块列表是有效用户选择。结果按优先级两列排列，每个模块独立分页，每页六条。

| 模块 | 复用接口 | 边界/缺失情况 |
| --- | --- | --- |
| 用户 | 按能力选择 `/api/mobile/v1/leaderboard` 或 `/api/community/leaderboard` | `days=all&positive_only=0&search=…`；搜公开昵称/身份，包含零 AC。这是排行榜公开成员范围，**不是完整成员目录 API**。缺少 `public_member_id` 时禁用主页跳转，不猜 QQ |
| 论坛 | `api.publicPostsPath` 按能力选择移动/旧论坛接口 | 标题与正文搜索；移动接口保留作者公开 ID；不要写死旧 `/api/forum/posts` |
| Wiki | `GET /api/wiki/search` | 公开文章搜索；文章直达使用 `wiki_slug` |
| 题目 | `GET /api/me/problems` | 需登录，`tag=关键词&scope=all`；全局搜索允许跨平台，不改变独立题库的默认 CF 筛选 |
| 比赛进度 | `GET /api/me/problems/tracker` | 需登录，本人目录中的比赛/题目，仍受已采集目录限制 |
| 我的话题/话题收藏/云端草稿 | `/api/forum/mine/posts`、`/api/forum/mine/bookmarks`、`/api/forum/drafts` | 需登录，在各接口最近至多 100 条内本地筛选返回字段；不能描述为全历史服务端搜索 |
| 社团题单/按题讨论/错题本 | 尚无可复用的对应搜索接口 | 保留可添加模块，显示红色圆角“无API接口”，不补假内容 |

缺失搜索接口并不意味着可以把 `/api/admin/members` 暴露给普通用户；管理员成员查询会返回 QQ、学校等私有资料。完整公开成员目录如需超出公开排行榜范围，须另行约定接口。

## 仍缺的业务接口与不需要接口的部分

基准为 main `f30cf10` 的代码核查，不是服务器部署证明。其余缺失能力保留第二优先级，本轮不新增业务后端。

| 能力 | App 既有占位路径 | 网页已有基础 / 尚缺部分 |
| --- | --- | --- |
| 社团题单 | `GET /api/club/sheets` | Web 有随机训练，尚无教练题单下发、截止和成员完成进度 |
| 按题讨论 | `GET/POST /api/club/problem-discussions` | Web 有泛论坛、评论、审核、举报；尚缺平台+题号关联与讨论标签检索 |
| 私人错题本 | `GET/PUT/DELETE /api/me/club/mistakes` | Web 有收藏；尚缺私人错因笔记/标签。退休笔记接口不能代替 |
| 间隔补题复习 | `GET/PUT /api/me/club/reviews` | Web 有赛事六态；尚缺复习阶段、到期和1/3/7天推进 |
| 每日目标与打卡 | `GET/POST /api/me/club/checkin` | Web 有汇总和活跃日；尚缺目标、达标和幂等打卡 |
| 完整公开成员搜索 | 暂复用公开排行榜 | Web/移动已有公开ID、资料和已发布话题；完整成员目录超出现有搜索范围 |

这些 `/club/` 路径是客户端已有约定，当前仓库尚无对应后端路由；后续需先确定契约，不能把界面存在当作API已实现。本轮搜索还需要对应的关键词/分页契约。

更新分发使用GitHub公开静态 JSON/APK，不需要业务 `/api/mobile/v1/releases/*`；自站客户端与镜像已从本PR拆分，另待配置和review。相册背景、裁剪、主辅色、透明度、本机主题、搜索设置/历史、通知时间均本机保存，不需要上传接口。公开成员ID/平台题数/已发布话题已有移动接口，不再列为缺失；OJ绑定继续提示到网页或联系管理员。

## 便捷管理权限与契约

账号设置仅在服务端会话确认为 `admin/root` 时显示入口。页面进入、重新可见及写操作前在后台验证会话；实际 API 仍由服务器鉴权。普通成员即使启动内部 Activity 也不能看到管理数据。

| 手机操作 | 既有接口 | 关键约束 |
| --- | --- | --- |
| 话题审核 | `GET /api/forum/moderation/posts`、`POST …/posts/{id}` | 通过/退回携带当前 `content_version`；退回原因必填，冲突刷新后重审 |
| 举报处理 | `GET /api/forum/moderation/reports`、`POST …/reports/{id}` | resolve/dismiss 仅处理举报记录，不自动删除原话题 |
| 同步任务 | `GET /api/tasks`、`POST /api/tasks/{id}/cancel` | 只允许取消仍可取消的任务；失败不自动重复写 |
| 成员查询 | `GET /api/admin/members`、`GET /api/member/{qq}` | 搜索、分页和只读资料；不进入通用响应缓存 |
| 生成训练/挑战历史 | `POST /api/challenge/start`、`GET /api/challenge/list` | 指定成员、平台及有效难度，标签可空；默认 CF 1000、AtCoder 800、洛谷“普及-”、牛客“2星”，切换平台重置对应选项，提交前校验；一次生成一题，不是普通成员的三档训练流程 |
| 指定成员复盘 | `GET/PUT /api/contest/reviews` | 精确携带成员与比赛、题目；六态与网页一致 |
| 比赛播报 | `GET/PUT /api/settings/contest-report` | 北京时间 HH:MM；修改/关闭前确认全站影响 |

批量开户、Excel/CSV、重置密码、角色授权、OJ 绑定变更、题库采集、CF 选题、Wiki 编辑与复杂全局设置留在 Web。完整后台外链打开系统浏览器，需单独登录，不向浏览器传 Cookie、密码或 Token。管理页面没有在生产执行试写。

## 不可破坏的关联

1. **会话与网络锁**：ApiClient 由 Application 初始化；Activity 重建不能在主线程调用 `setBaseUrl`、`refreshSession` 或同步网络方法。接口写操作经 CSRF 和服务器鉴权，不凭 UI 角色放行。
2. **草稿归属**：编辑器和自动保存必须绑定当前账号及草稿代次。恢复编辑页时同步内容和控件；文件选择期间保存导入归属，不能把 A 的文本写入 B。
3. **页面与迟到响应**：页面序号、会话代次及模块槽位均校验后再显示；返回使用页面栈。重复点击只启动一个页面/弹窗，不能排队重叠。
4. **缓存与报错**：普通读取先回显缓存再请求，10 秒连接预警并持续重试；用户关闭只隐藏警告，成功显示绿色“重连成功”3秒。写失败显示红提示，**不能自动重发审核、发帖、评论等写操作**。区分无接口、无网络、无权限和有效空结果。
5. **外观**：模块圆角、按钮间距和主辅色由共用样式控制；不写死普通按钮颜色覆盖个性化设置。警告与标题留间距。
6. **更新安全**：清单必须 HTTPS、有界大小；APK 验证大小/哈希/包名/更高版本/设备 API/当前签名。自定义清单失败不偷偷切换官方源。安装需系统确认；默认自动检查，不自动下载安装。
7. **发布边界**：APK、签名、SSH 私钥、缓存不入源码 Git。源码 PR 经别人 review；用户确认后才由有权限成员合并/创建 Tag。静态镜像不放业务替换目录，不修改网站后端或数据库。

## 修改与验收顺序

- 先读仓库 README、[协作规范](TCrB-AI项目工程规范.md)和本文件，核对最新 `main`、Git 差异与实际运行入口。
- 用既有公开/本人/管理 API，缺失时明确挂空；新增后端接口或改变业务契约先告知用户并约定范围。
- 版本同时更新 `build.gradle` 与 `assets/releases/history.json`。同渠道必须沿用签名且 versionCode 递增。
- 单元测试、Lint、构建及受影响的真实 Activity 流程通过后再打包；回归见 [本轮实施与验收](android-v0.2.17.md)。不要把测试夹具当线上数据。
- 只暂存本任务路径，检查敏感信息、`git diff --cached --check`，源码与文档分别提交；PR 写清测试与尚未部署的配置。新增文档在根 README 添加入口。

当前GitHub发布配置见 [Tag发布](android-tag-release-v0.2.14.md)。自站更新另开PR；原讨论保留在 [PR #100](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/100)。
