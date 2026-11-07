# Android 修改标准与模块关联（v0.2.23）

状态：本轮实现说明，待跨人评审；2026-11-07。以实际代码与测试结果为准。适用工程 `Android_APP/app/`，不改变仓库协作规范。维护责任、人员署名、修改步骤和发布交接另见[App 修改与维护交接规范](android-maintainer-handover.md)。

## 目录与修改入口

Java 路径前缀为 `Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/`。

| 入口 | 职责 | 修改时必须联查 |
| --- | --- | --- |
| `AcmApplication`、`ApiClient`、`SessionVault` | 进程共享会话、CSRF、权限、缓存和加密凭据 | 退出、切账号/服务、Activity 重建、禁止主线程等待网络锁 |
| `LoginGate`、`MainActivity`与`AppUpdates` | 未登录 UI 门禁及会话失效回登录 | 未登录只显示登录表单；唯一例外是已有本机注销回执查询。隐藏顶栏/底栏/设置，内部子页启动或恢复不能旁路；登录前不显示更新弹窗，不能将客户端门禁当成后端鉴权 |
| `GithubCredits`、`CreditsViews`、`AboutActivity`、`UpdateActivity`与`assets/releases/credits.json` | 版本负责人、评审协作、特别鸣谢与离线头像 | 主体与自动化职责分开，来源链接和快照日期保留；早期汇总评审注明范围，当前未完成评审留空；名单、头像、版本日志同步验证，维护交接见独立规范 |
| `MainActivity`、`NavigationStack`、`PageMotion` | 首页/排名/题库/发帖/个人中心/账号设置及原生详情 | 五个平行栏目无动画，子页面右入/右出；临时快照取消与释放，`external_navigation`、详情返回、草稿归属、搜索入口防重 |
| `SearchActivity`、`SearchModules`、`SearchHotPosts` | 搜索顶栏、首次聚焦、热搜、结果、模块设置和历史记录 | 热搜仅首批30条热门候选，按真实阅读量选至多4条；异步返回不抢输入焦点，搜索设置入口唯一，公开 ID、本人接口范围、缓存及模块独立失败 |
| `ModuleOrderView`、`ModuleDragPhysics`、`ModuleEdgeScroll` | 整卡纵向拖拽、90%缩放、边框提前让位、逐项弹簧传播与慢速边缘滚动 | 所有行均受列表上下边界约束，不能只限制选中行；开启列表裁剪；边缘速度按经过时间及密度计算，不能按每帧固定距离；原始行身份不等于bringToFront后的绘制次序；首个拦截事件、取消不保存、松手保存、无障碍及父滚动拦截继续联查 |
| `ModalDialogs`、`KeyboardInputs`、窗口样式 | 普通弹窗/全屏表单和软键盘 | 自定义全屏Dialog安装编辑器后清除阻挡IME的窗口标志；仅搜索入口主动显示，普通表单点击唤起；不绕过权限/防重 |
| `MobilePageActivity`、`PullRefreshLayout`、`PageRefresh` | 搜索与便捷管理的页面壳、缓存读取、串行后台操作 | 页面代次、会话代次、槽位绑定；下拉只重复注册的读取，排序长按不能被父滚动抢占，不得刷新草稿或重放写操作 |
| `AdminQuickActivity`、`AdminApiPolicy`、`AdminMemberEdits` | 手机便捷管理和 API 白名单 | 服务端角色重验证、CSRF、审核版本、敏感内容禁止通用缓存 |
| `SyncTaskResult` | 同步任务的数值结果展示 | `-1`也可能是已有成员抓取失败，显示通用“同步失败”；不能据此推断成员不存在。新增条数与未绑定/抓取异常/暂停仍各自展示 |
| `ChallengeDifficulty` | 管理员单题训练的难度选项和默认值 | 与 `acm_api/difficulty.py` 的有效值及网页训练默认值一致；切换平台同步难度，空选项不得发送请求 |
| `WebFeaturesActivity` | 通知/投稿进度/比赛进度/Wiki | Wiki 站内练习相对链接进入原生题面，外链 HTTPS 校验 |
| `WikiCatalog`、`WikiOutline`、`WikiReaderNavigation`、`ContentView`及`reader/content.js` | Wiki分类路径、文章标签、章节目录/高亮与阅读位置 | 只读公开接口；分类和文章独立失败；从清理后的实际DOM取标题，代码块不算目录、重复标题ID唯一；无JS应用桥，章内偏移/历史版本/转屏/返回及动态布局必须联查 |
| `ProblemTags`、`ProblemTagPicker`、题库与搜索/比赛进度 | 原始标签候选搜索、完整标签精确筛选 | `tag`关键词与`problem_tag`完整标签分开编码；真实候选、平台切换清标签、筛选归第一页、翻页/返回/重建保留、单窗防重及会话代次 |
| `OjBindingsActivity`、`OjBindingState` | 本人 OJ 绑定列表、归属核验、绑定/改绑/解绑与同步 | 复用 `/api/me/profile` 的 `bindings` 能力；是否绑定取账号字段而非 AC 数；确认请求必须核对实际输入与验证码所属账号；密码/确认不持久化，写入不自动重试，返回个人中心/账号页刷新 |
| `AccountClosureActivity`、`AccountClosureFlow`、`AccountClosure`、`SessionVault`及`MainActivity`登录页 | 本人账户注销、实时开关、确认和结果回执 | 独立加密回执先保存再提交；未登录时仍须有本机回执查询入口；当前密码不持久化；管理员不能提交；转屏/断网/重启只查询，不重放POST；已明确的提交前拒绝可清回执，查询限流不得清理；必须匹配回执与提交时间才报成功，同QQ新代账号不可被旧回执退出 |
| `ClubActivity`、`TrainingReminder` | 题单、讨论、错题、复习、打卡和本地提醒 | 缺失接口保留真实报错，通知授权、返回来源页 |
| `CloudDrafts` 与主页面编辑器 | 云端多草稿和自动保存 | 账号+草稿代次；切换草稿、返回旧页、迟到写入、Markdown 导入归属 |
| `PdfActivity`、`ContentView`、阅读器资源 | PDF、Markdown/公式/代码与图片 | 缩放/翻页/复制、受限媒体地址、缓存边界 |
| `ImagePreviewActivity`、`PageRefresh`、`ApiClient.MediaFormatException` | 图片失败后的原页手动/自动恢复 | 仅连接失败重试；格式/尺寸/权限错误不循环；十秒预警、关闭仍重试、成功三秒消失、会话代次与退出取消 |
| `StorageActivity`、`TemporaryStorage`、`HelpActivity`、`AppUpdates` | 三块存储管理及本机帮助说明 | 文件操作在后台；保留凭据、主题、草稿、活动PDF与近期分享；安装包单独清理，下载/校验/安装期间拒绝；新页面继续强制登录 |
| `AppAppearance`、`MobileStyle`、`ProfileCover`、`LocalThemes` | 主题、主辅色、全屏背景、模块/控件透明度 | 深浅色、状态栏、原位变色、保存/预览/删除本机主题 |
| `ThemePackage`、`LocalThemes`、`ProfileCover` | `.acmtheme`格式、隔离安装、原图字节与非破坏性裁剪 | [格式规范](android-theme-package-v1.md)；布尔选项、主辅色/透明度、模板浅深配色、原图及裁剪同时往返；文件I/O不在主线程，先校验后登记，导入不覆盖当前外观 |
| `ThemeShareProvider`、`AppearanceActivity` | 后台生成私人主题文件并调用系统分享 | 独立只读附件、ClipData读取授权、随机文件名与缓存回收；不共用APK Provider，不包含账号字段，不自动发送QQ/微信消息 |
| `OfficialThemeView`、`theme-renderer/` | 原Vue/CSS/SVG离线主题层，无原生JS桥 | [源文件关联](android-official-theme-adaptation-v0.2.17.md)；原源变化重跑构建工具和指纹检查，禁止用重新描摹替代；原生控件仍使用共享样式 |
| `AppUpdates`、`UpdateManifest`、更新页面与 Provider | 检查、下载、校验及系统安装 | 当前GitHub单源、取消/重建/进程恢复、包名版本签名、更新日志 |
| `tools/create_update_manifest.py`、`tag_release.py` | 同一 APK 的清单和GitHub Release事务 | `.github/workflows/android-release.yml`、签名渠道、不可变目录和 latest |

`AdminActivity`、`BrowserActivity`、`UpdateManager` 与 `assets/admin/` 被当前 Gradle 排除；它们是历史代码。`prototype/` 也是历史浏览器原型，不能通过修改这些文件来声称 Android 已实现。App 不直接访问数据库，不能内置 `/internal/v1/*` 的 Bot Token。

## 搜索接口矩阵

默认顺序为 **用户 → 论坛 → Wiki → 题目**。顺序、启用模块和最近十条记录仅保存在本机，键为 `global_search_modules`、`search_history`、`record_search`。空模块列表是有效用户选择。结果按优先级单列排列，每个模块独立分页，每页六条。空搜索页顶栏为返回、输入框和圆形猫娘搜索图标，下方依次为热搜、搜索历史/历史记录、唯一一个搜索设置；首次空查询入口自动聚焦并弹键盘，提交与后台返回不抢焦点。

热搜复用 `api.publicPostsPath("")+"?sort=hot&page=1&page_size=30"`，支持移动接口的 `items` 与旧接口的 `rows`，按 `views_count` 降序取最多4条并去重，标题点击进入原生话题。后端 `hot` 是置顶优先的综合热度，不是全站阅读量排序；不能将该候选范围描述为全站前四。空结果、断网和缺少接口继续使用真实状态，不植入默认热搜。

首页通过Intent传入的首次非空 `query` 与搜索页按钮/键盘提交共用 `SearchActivity.submit`，统一去除首尾空白、限制100个Unicode码点，并按记录开关更新最近十条、去重。Activity状态恢复只渲染已保存查询，不能将旧词重新置顶；进入搜索设置等非搜索模式也不写入查询记录。

| 模块 | 复用接口 | 边界/缺失情况 |
| --- | --- | --- |
| 用户 | 按能力选择 `/api/mobile/v1/leaderboard` 或 `/api/community/leaderboard` | `days=all&positive_only=0&search=…`；搜公开昵称/身份，包含零 AC。这是排行榜公开成员范围，**不是完整成员目录 API**。缺少 `public_member_id` 时禁用主页跳转，不猜 QQ |
| 论坛 | `api.publicPostsPath` 按能力选择移动/旧论坛接口 | 标题与正文搜索；移动接口保留作者公开 ID；不要写死旧 `/api/forum/posts` |
| Wiki | `GET /api/wiki/search` | 公开文章搜索；文章直达使用 `wiki_slug` |
| 题目 | `GET /api/me/problems` | 需登录，`tag=关键词&scope=all`；可组合`problem_tag=完整标签`；全局搜索允许跨平台，不改变独立题库的默认 CF 筛选 |
| 比赛进度 | `GET /api/me/problems/tracker` | 需登录，本人目录中的比赛/题目；可独立组合关键词与完整标签，仍受已采集目录限制 |
| 我的话题/话题收藏/云端草稿 | `/api/forum/mine/posts`、`/api/forum/mine/bookmarks`、`/api/forum/drafts` | 需登录，在各接口最近至多 100 条内本地筛选返回字段；不能描述为全历史服务端搜索 |
| 社团题单/按题讨论/错题本 | 尚无可复用的对应搜索接口 | 保留可添加模块，显示红色圆角“无API接口”，不补假内容 |

缺失搜索接口并不意味着可以把 `/api/admin/members` 暴露给普通用户；管理员成员查询会返回 QQ、学校等私有资料。完整公开成员目录如需超出公开排行榜范围，须另行约定接口。

题库、比赛进度及全局对应模块共用 `GET /api/me/problems/tags?platform=…` 的真实原始标签候选；候选窗口可以模糊搜索标签名，但提交时使用忽略大小写的完整标签匹配。不要以 `labels` 二次分类或拆分后的词代替。题库独立关键词与输入草稿进入页面栈，后台结果只更新列表，不能重建正在编辑的输入框。详情和本轮本地验证见[原始标签筛选与搜索](android-problem-tags-local-2026-11-06.md)。

Wiki完整目录与阅读导航的本地适配见[android-wiki-navigation-local-2026-11-06.md](android-wiki-navigation-local-2026-11-06.md)。目录使用`/api/wiki/navigation`、分类说明使用`/api/wiki/categories/{id}`，正文与公开历史使用既有接口。阅读目录不需要新后端：标题与坐标从已清理且完成排版的正文生成，当前章节跟随外层原生滚动。不要把WebView的内部滚动当成整个页面阅读位置，也不要为锚点放开任意文件、脚本或登录Cookie访问。

## 仍缺的业务接口与不需要接口的部分

基准为 main `f30b33cf` 的代码核查，不是服务器部署证明。其余缺失能力保留第二优先级，本轮不新增业务后端。

| 能力 | App 既有占位路径 | 网页已有基础 / 尚缺部分 |
| --- | --- | --- |
| 社团题单 | `GET /api/club/sheets` | Web 有随机训练，尚无教练题单下发、截止和成员完成进度 |
| 按题讨论 | `GET/POST /api/club/problem-discussions` | Web 有泛论坛、评论、审核、举报；尚缺平台+题号关联与讨论标签检索 |
| 私人错题本 | `GET/PUT/DELETE /api/me/club/mistakes` | Web 有收藏；尚缺私人错因笔记/标签。退休笔记接口不能代替 |
| 间隔补题复习 | `GET/PUT /api/me/club/reviews` | Web 有赛事六态；尚缺复习阶段、到期和1/3/7天推进 |
| 每日目标与打卡 | `GET/POST /api/me/club/checkin` | Web 有汇总和活跃日；尚缺目标、达标和幂等打卡 |
| 完整公开成员搜索 | 暂复用公开排行榜 | Web/移动已有公开ID、资料和已发布话题；完整成员目录超出现有搜索范围 |

这些 `/club/` 路径是客户端已有约定，当前仓库尚无对应后端路由；后续需先确定契约，不能把界面存在当作API已实现。本轮搜索还需要对应的关键词/分页契约。

更新分发使用GitHub公开静态 JSON/APK，不需要业务 `/api/mobile/v1/releases/*`；自站客户端与镜像已从本PR拆分，另待配置和review。相册背景、裁剪、主辅色、透明度、本机主题、搜索设置/历史、通知时间均本机保存，不需要上传接口。公开成员ID/平台题数/已发布话题已有移动接口，不再列为缺失；本人OJ绑定的新本地实现见下节，不改变服务器已开放的平台范围。

## 本人 OJ 绑定（本地新增，2026-11-06）

个人中心的单平台通过题数卡在本人未绑定时显示“绑定”，替代题数位置；已绑定且零AC显示0，不显示绑定按钮；ALL与他人主页不展示操作。账号设置 → 个人资料 → OJ账号绑定进入原生列表，已绑定展示用户名和“修改”，未绑定展示“绑定”。

状态来自 `GET /api/me/profile` 的 `user` 与 `bindings`；不凭平台名称假定服务可用。绑定详情复用 `POST /api/me/bindings/{platform}/verification`、`confirm`、`sync` 和 `DELETE /api/me/bindings/{platform}`。当前正式后端仅CF的 `self_service=true`，其他平台说明联系管理员；已绑定平台仍可按既有接口解绑和同步。旧服务没有 `bindings` 时只读账号，并说明缺少接口。

CF申请验证码后，将验证码保存到公开资料再确认；改绑、解绑及已有账号的归属核验携带当前平台账号、ACMForever登录密码和显式确认。按后端原约束解释清理影响，不收集OJ密码，不使用管理员接口。密码/勾选/验证码不写实例状态；恢复时重新读服务器待验证状态。网络失败不自动重发写入，服务器拒绝时保留原绑定。归属核验写请求读取超时25秒，与网页一致，其余请求及10秒读取预警不变。

`confirmationBody`必须接收当前账号输入并与服务器 `challenge.account` 比较，不能使用可被失败重新申请改写的本地候选值作为验证码归属。改填账号后，本地校验失败或网络请求未到达服务器，均不得让旧 `verification_id` 绑定输入以外的账号；大小写与首尾空白按账号原规则处理。

详情与验证见 [android-oj-bindings-local-2026-11-06.md](android-oj-bindings-local-2026-11-06.md)。此前功能对照节点保留当时结论，不覆盖历史。

## 便捷管理权限与契约

本人注销复用现成 `/api/me/account-closure/preview`、`POST /api/me/account-closure` 与 `/api/account-closures/{request_id}`，不属于缺失接口。开关从会话实时获取，App不修改后端环境变量。详情见[本人账户注销本地实现](android-account-closure-local-2026-11-06.md)。普通注销需要当前登录密码、CSRF、幂等键与独立回执；admin/root先完成交接降级。后端私有数据删除与公共内容匿名规则不能缩减成“退出即成功”。

注销错误分类必须区分提交与回执查询：现有服务端在提交事务前返回的 `429 / RATE_LIMITED` 是明确拒绝，客户端清除待确认回执，保留会话并允许手动重新检查，不自动再次POST。只有状态码与业务码同时匹配才使用此规则；裸429、未知业务码、超时及5xx继续保留恢复信息。回执GET即使返回同样的 `429 / RATE_LIMITED` 也不能证明注销未发生，不得清回执或切换到新提交。

注销POST的 `401 / AUTH_REQUIRED` 也属于明确提交前拒绝，可清除待确认回执并引导重新登录后手动检查。不能将该规则扩大到裸401、未知业务码或5xx；回执GET的认证失败仍属结果不明，必须保留原回执，且不能清理当前正常会话。

注销回执的恢复入口不能依赖正常登录。`MainActivity.showLogin()` 同时覆盖启动时未登录和刷新会话失败后显示登录表单的路径；有本机密文时显示“查询注销结果”。UI只检查密文存在，不解密、不取Keystore、不获取ApiClient网络锁；真正读取在注销工作线程执行。恢复只能查询旧回执，不能自动登录、重新预览或重放POST；服务器注销开关关闭也不能封住回执查询。普通退出登录与会话失效不得删除待确认回执；只有明确拒绝或用户确认已完成结果时按现有规则清理。

账号设置仅在服务端会话确认为 `admin/root` 时显示入口。页面进入、重新可见及每次管理读写前在后台验证会话；实际 API 仍由服务器鉴权。普通成员即使启动内部 Activity 也不能看到管理数据。

| 手机操作 | 既有接口 | 关键约束 |
| --- | --- | --- |
| 话题审核 | `GET /api/forum/moderation/posts`、`POST …/posts/{id}` | 通过/退回携带当前 `content_version`；退回原因必填，冲突刷新后重审 |
| 举报处理 | `GET /api/forum/moderation/reports`、`POST …/reports/{id}` | resolve/dismiss 仅处理举报记录，不自动删除原话题 |
| 同步任务 | `GET /api/tasks`、`POST /api/tasks/{id}/cancel` | 只允许取消仍可取消的任务；失败不自动重复写 |
| 成员管理 | `GET /api/admin/members/options`、`GET /api/admin/members`、`GET/PATCH /api/admin/members/{qq}`、`GET /api/member/{qq}` | 关键词/学校/身份筛选、完整卡片；整卡进入详情，资料修改带账号代际及资料版本，绑定变更确认旧绑定/版本及清理影响；数字0/1和布尔启停标志兼容，敏感资料不进通用缓存 |
| 成员登录账号 | `POST /api/admin/web-accounts/{qq}/reset-password`、`PATCH /api/admin/web-accounts/{qq}` | 初始密码、启停和Root角色操作；管理账号仅Root可操作，服务端保护最后Root。密码不进实例状态、日志或缓存，操作后重新验证会话 |
| 生成训练/挑战历史 | `POST /api/challenge/start`、`GET /api/challenge/list` | 指定成员、平台及有效难度，标签可空；默认 CF 1000、AtCoder 800、洛谷“普及-”、牛客“2星”，切换平台重置对应选项，提交前校验；一次生成一题，不是普通成员的三档训练流程 |
| 指定成员复盘 | `GET/PUT /api/contest/reviews` | 精确携带成员与比赛、题目；六态与网页一致 |
| 比赛播报 | `GET/PUT /api/settings/contest-report` | 北京时间 HH:MM；修改/关闭前确认全站影响 |

按本轮需求，手机便捷管理增加单个成员的资料/四个OJ绑定、密码和账号启停；Root可改角色。普通成员自身绑定使用上节单独的本人接口，不能借用管理接口。批量开户、Excel/CSV、校OJ、题库采集、CF 选题、Wiki 编辑与复杂全局设置留在 Web。完整后台外链打开系统浏览器，需单独登录，不向浏览器传 Cookie、密码或 Token。管理页面没有在生产执行试写。

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
- 单元测试、Lint、构建及受影响的真实 Activity 流程通过后再打包；回归见 [本轮实施与验收](android-v0.2.19.md)。不要把测试夹具当线上数据。
- 只暂存本任务路径，检查敏感信息、`git diff --cached --check`，源码与文档分别提交；PR 写清测试与尚未部署的配置。新增文档在根 README 添加入口。

当前GitHub发布配置见 [Tag发布](android-tag-release-v0.2.14.md)。自站更新另开PR；原讨论保留在 [PR #100](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/100)。

## v0.2.19新增关联

- `ModuleOrderView`负责实际卡片纵向移动、90%缩放和让位动画；仅松手保存顺序，取消/离开恢复，禁止系统任意横移拖影。删除与添加继续改同一`SearchModules.KEY`。
- `PullRefreshLayout`只触发`PageRefresh`登记的读取；不能调用发帖/审核/改密等提交函数。新增页面必须考虑滚动顶部判定、长按、输入、无障碍和会话代次。
- `AppUpdates`将尝试时间与成功时间分开，六小时依据成功结果，失败一分钟防抖；更新页进入即手动检查，同次Activity重建不重复。GitHub发布、自站PR及下载校验链不变。
- 官方横幅背景与交互画布分层，使用原CSS装饰；不要再覆盖模板内部图谱/地形的不同尺寸。详情见[android-v0.2.19.md（本轮范围、权限与验收）](android-v0.2.19.md)。

## v0.2.21拖动边界与滚动速度

- `ModuleDragPhysics`对选中模块、邻居目标及积分后的实际位置统一限制为`0..列表总高-该行高度`，触界清零该行速度；列表总高由各行实际高度及间距确定。到达上下边界仍允许进入首尾槽位，不能仅依赖不同高度卡片的中心越过。修改避让逻辑须验证首尾受压、不同高度及快速反向，禁止把负坐标当成向上让位成功。
- `ModuleOrderView`开启子元素裁剪，模块不能覆盖搜索设置的历史记录/添加操作区；90%缩放、纵向跟手和松手保存继续保留。
- `ModuleEdgeScroll`最高96dp/秒，边缘深度平方调速、120ms加速，离开边缘立即停止，改变方向清旧速度，单帧最多计50ms。保留小数像素并积分加速过程，60Hz/120Hz同时间距离应一致；不能恢复为每帧固定9dp。
- v0.2.21 已随 PR #110 合并并由 Tag 发布；下述[android-v0.2.21.md](android-v0.2.21.md)保留当时验证记录。本轮 v0.2.22 另提 PR 交其他成员评审，不合并或发布，不改自站或发布链。网站共享后端变化另见[网站更新核对](web-updates-since-android-v0.2.20.md)，不代表已部署或已在App专门适配。
