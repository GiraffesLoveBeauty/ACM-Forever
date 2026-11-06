# 网页与 App 功能差距对照：2026-11-06 / v0.2.21

状态：本地源码核对记录，不是线上验收或实施承诺。本轮只增加对照和节点记录，不改功能、不更新 APK、不推送、不上传 PR；自站配置继续等待。

## 1. 本次对比节点

节点 ID：**WEB-APP-20261106-01**。快照时间：**2026-11-06 18:25:42（北京时间）**；远端 main 已用只读 `ls-remote` 核对。

| 项目 | 固定基准 |
| --- | --- |
| 网页 / 正式后端源码 | `main` = `040bfb3ce7a55c08cbf23ac066eadb4a50cf1426`，合入 PR #109 |
| 本地 HEAD | 同为 `040bfb3ce7a55c08cbf23ac066eadb4a50cf1426` |
| 本地任务分支 | `codex/android-v0.2.21-drag-bounds` |
| 本次 App | **本地 v0.2.21 / versionCode 35**，包含尚未提交的搜索排序边界和慢速边缘滚动修复 |
| 已发布 App | `v0.2.20` / code 34，Tag 提交 `b6a9bfe9171cbb55be6b25b9f03d6424489899b6`；不是本次本地候选 |
| 本地候选 APK | `Android_APP/dist/acmforever-0.2.21-debug.apk`，3,334,544 字节；SHA-256：`68912db326337b0657c840cc5115ee0fc7370680cbaedfe48cb0f0936334df47` |
| 可追溯快照 | [web-app-node-2026-11-06-v0.2.21.json](web-app-node-2026-11-06-v0.2.21.json)：记录核对时间、源码树指纹和未提交代码文件的哈希 |

核对范围：网页 `feat/web/src`、正式服务 `feat/api`、翻译等本地验收服务 `local_demo`，以及 Android 当前 Gradle 实际包含的运行代码。排除旧静态网页、历史 `prototype`、Gradle 排除的 `AdminActivity` / `BrowserActivity` / `UpdateManager` 和 `assets/admin/`，也不把未合入的自站分支计入当前能力。

“有”表示源码有入口和处理逻辑，不保证服务器已部署、开关已启用或数据已采集。本次没有登录生产账号、执行 AI 请求、触发采集或重跑业务测试。此前 App 本地验证见 [v0.2.21 验收记录](android-v0.2.21.md)，不作为网页全流程验收。

本表取代 [2026-11-03 / v0.2.0 旧对照](../Android_APP/docs/网页与App功能对照目录-v0.2.0-2026-11-03.md) 作为后续比较基线；旧文保留当时记录，不能继续用其“App 无收藏/多草稿/主题”“社团题单已有完整后端”等结论描述现在。

## 2. 直接差距结论

| 类别 | 当前差距 |
| --- | --- |
| 网页有正式接口，App 尚未接入 | 本人 OJ 归属核验/绑定/改绑/解绑/同步；账号注销与结果回执；原始题目标签精确筛选；Wiki 完整目录与阅读导航；批量开户、Excel/CSV、CF 选题、Wiki 编辑等重管理 |
| 网页已有界面，但正式服务仍缺接入 | 题面 AI 翻译、中文算法标签与人工修正、有效标签多选组合筛选、后台数据库与 AI 处理面板；本地验收接口不等于生产接口 |
| App 有、网页未做同等入口 | 多模块统一搜索及本机排序/历史、公开成员主页、平台 ALL/切换面板、相册背景裁剪、透明度、`.acmtheme` 完整主题分享、本地通知、APK 更新流程 |
| App 有界面，但两端仍缺对应正式业务接口 | 社团题单、按题讨论、私人错题本、间隔复习、每日目标与打卡；本地提醒设置能独立使用，不能据此说训练闭环已打通 |
| 两端主体功能已共有 | 登录与改密、论坛、Markdown/图片/预览、话题收藏、多草稿、投稿修订、通知、基础题库/PDF、排行榜、今日训练与六态复盘、Wiki 阅读、基础审核和单成员管理 |

上述差距不是全部都需要照搬：OJ 操作暂留网页、批量管理留 Web，是此前确认的分工；本表如实登记，不自动改变分工。

## 3. 普通成员功能逐项对照

### 3.1 账号、资料与公开身份

| 功能 | 网页 | App | 差距与接口状态 |
| --- | --- | --- | --- |
| 登录、退出、首次强制改密、修改密码 | 有 | 有 | 共用认证/CSRF；客户端会话保存方式不同，不是两套账号 |
| 记住账号 / 密码 / 自动登录、密码小眼睛 | 页面没有这三个显式开关或小眼睛，浏览器可自行管理凭据 | 有显式选项、加密凭据及小眼睛 | App 额外本机能力；不能把浏览器会话保持误写为网页完全不能保持登录 |
| 昵称、头像上传与恢复默认 | 有 | 有 | 基本共有 |
| 本人 OJ 账号摘要 | 有 | 有，只读 | 基本共有；不能把查看绑定写成已支持改绑 |
| OJ 自助核验、首次绑定、改绑 | 有，当前仅 CF 开放归属自助核验，其他平台提示联系管理员 | 明确提示 App 不支持，到网页或联系管理员 | 现有正式 `/api/me/bindings/{platform}/verification`、`confirm` 可复用；需遵守服务端平台开放范围 |
| OJ 解绑与本人手动同步、同步状态/来源 | 网页按服务端能力展示操作、进度及管理员导入待核验信息 | 未接入自助操作，只读绑定提示 | 正式绑定删除及 `/sync` 路由存在；不是缺后端接口 |
| 账号注销、影响预览、再次验证、回执查询 | 有页面与正式路由 | 无原生入口/流程 | 正式后端已有，`ACM_ACCOUNT_CLOSURE_ENABLED` 默认关闭；不能直接描述为线上已开放 |
| 本人通过题数、最近 AC | 有 | 有 | App 最近 AC 进入站内题面；网页同时有原题/题库相关入口 |
| 他人公开主页、各平台题数及公开话题 | 当前 Vue 路由未做独立公开成员页，论坛/榜单显示公开摘要 | 有，从作者或榜单进入，依赖公开 ID | App 使用已有移动公开接口；网页不能把管理员私有成员详情当公开页 |
| 平台统计切换 / ALL | 统计卡片为主 | 一页内 ALL 与平台 logo 切换，题数/最近 AC 分区 | App 特有呈现方式，数据来源共用 |

证据：[Auth](../feat/web/src/views/Auth.vue)、[Home](../feat/web/src/views/Home.vue)、[OjBindings](../feat/web/src/components/OjBindings.vue)、[AccountClosure](../feat/web/src/views/AccountClosure.vue)、[正式绑定逻辑](../feat/api/acm_api/binding_service.py)、[注销开关与路由注册](../feat/api/app.py)、[App 主页面/账号/成员页](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MainActivity.java)、[移动公开接口](../feat/api/acm_api/mobile_api.py)。

### 3.2 论坛、发帖与通知

| 功能 | 网页 | App | 差距与边界 |
| --- | --- | --- | --- |
| 分类、话题搜索、最新/热门/待回答、分页 | 有 | 有 | 核心共有；网页分区/筛选栏，App 漏斗和移动卡片 |
| 热门展示 | 论坛热门候选展示 | 搜索首页取首批30条热门候选，按阅读量取最多4条 | 都不能等同全站浏览量前四；App 无独立全站热搜 API |
| 话题正文、代码/公式、图片、阅读量 | 有 | 有 | 共用正文数据；渲染器与移动排版不同 |
| 评论、回复、Markdown 预览 | 有 | 有，另带格式快捷按钮 | 共用评论接口；App 发送时插入本地条目、失败提示，不重建整个详情 |
| 点赞、话题收藏、我的话题收藏 | 有 | 有 | 已共有，不再列成 App 缺失 |
| 举报、按权限删除话题 | 有 | 有 | 共用后端权限与状态 |
| 发帖 Markdown、图片上传、导入 `.md`、预览 | 有 | 有 | 已共有；App 格式工具分行，图片/Markdown 导入绑定当前账号与草稿 |
| 云端多草稿、自动保存、手动保存、删除与恢复保护 | 有 | 有 | 同账号草稿可跨端使用；App 保留草稿代次/迟到回调保护，不是仅有本机单草稿 |
| 投稿进度、审核原因、历史版本、修改重投 | 有 | 有 | App 发布后进入进度页；两端读取相同投稿数据 |
| 通知、未读筛选、单条/全部已读、定位话题评论 | 有 | 有 | 主流程共有；网页有顶栏通知组件，App 从常用工具进入通知中心 |

证据：[网页论坛](../feat/web/src/views/Forum.vue)、[话题详情](../feat/web/src/views/Post.vue)、[发帖编辑](../feat/web/src/views/Compose.vue)、[评论编辑器](../feat/web/src/components/CommentEditor.vue)、[投稿进度](../feat/web/src/views/MyPost.vue)、[通知](../feat/web/src/views/Notifications.vue)、[App 主页面](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MainActivity.java)、[App 草稿](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/CloudDrafts.java)、[App 通知/进度](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/WebFeaturesActivity.java)。

### 3.3 搜索

| 功能 | 网页 | App | 差距与边界 |
| --- | --- | --- | --- |
| 各页面局部搜索 | 论坛、排行、题库、Wiki 等分别查询 | 各列表仍有自己的筛选，另有统一搜索 | 查询范围不完全相同 |
| 用户→论坛→Wiki→题目的统一结果页 | 未做同等统一入口 | 有，单列按优先级分区、各模块独立分页 | App 复用多个现有接口，没有新增统一后端搜索接口 |
| 搜索模块添加、移除、拖动排序 | 无对应页面 | 有，包含本人话题/收藏/草稿/比赛进度等可选模块 | 本机保存；题单/讨论/错题搜索仍无 API |
| 最近10条历史、记录开关、删除、点击复搜 | 未做统一跨页历史管理 | 有，文字宽度词条换行 | App 本机能力 |
| 完整公开成员目录搜索 | 未做 | 暂借公开排行榜搜索 | 两端都没有完整公开成员目录；App 搜索包含零 AC，但仍受公开排行榜成员范围限制 |

证据：[网页路由](../feat/web/src/router.js)、[App SearchActivity](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/SearchActivity.java)、[模块定义与范围](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/SearchModules.java)、[搜索/缺失接口矩阵](android-modification-standard.md)。

### 3.4 题库、题面、翻译与算法标签

| 功能 | 网页 | App | 差距与接口状态 |
| --- | --- | --- | --- |
| 题库列表、平台/关键词、我已 AC、题目收藏、分页 | 有 | 有 | 基本共有；当前都按20条读取题库列表 |
| 默认平台和“全部平台” | 列表当前默认全部平台，另可指定平台 | 独立题库默认 CF，只提供单平台切换；统一搜索可跨平台 | 当前行为不同；不能继续说 App 已完全跟随最新版网页默认规则 |
| 原始标签精确下拉筛选 | 有，读取标签候选并传 `problem_tag` | 未做，现用 `tag` 文本查询 | 正式 `/api/me/problems/tags` 及 `problem_tag` 已存在，可复用 |
| 中文有效算法标签多选、全部/任一匹配、词表/计数 | 网页有界面；`tag_facets` / `labels` / `match` 由本地验收包装提供完整语义 | 无对应 UI 或请求参数 | 属于“网页+本地服务已做，正式后端未整合”，不是拿现成生产接口即可完整启用 |
| 比赛进度、CF/AtCoder、本人 AC/尝试/收藏状态 | 有题库内视图、表格和筛选 | 有独立比赛进度页、状态按钮、搜索/分页 | 主功能共有；App 未接网页的原始标签下拉和表格布局 |
| HTML/Markdown 题面、图示/公式、样例复制 | 有 | 有 | 主流程共有；具体题型/图片显示仍需数据验收 |
| PDF 翻页、缩放、适应宽度 | 有 | 有原生阅读器 | 已共有，不再列为 App 缺失 |
| 独立样例说明与官方样例 ZIP 附件入口 | 网页逐样例展示说明并提供受限官方 ZIP 链接 | 当前独立样例卡仅显输入/输出，没有逐附件入口；正文可能仍包含说明 | App 展示未完整跟上网页；现有详情数据可供适配，不必新增翻译接口 |
| 中文译文、原文保留、翻译状态/来源 | 有成员面板，可展开/收起已激活译文 | 无译文区域，只读 `statement_html` / `statement_text` | `/api/secondary/problems/{platform}/{id}` 目前仅注册在 `local_demo`，正式服务未接入 |
| AI 翻译预检/确认执行、异步任务状态 | 网页管理员面板+本地执行服务已有 | 无 | 先完成正式鉴权、持久目录及路由接入；成员看译文不应触发付费请求 |
| AI 标签、CF 映射、人工增删/替换/撤销、来源/审核历史 | 网页+本地服务已有 | 无 | 同属正式后端待整合；不能让 AI 自动覆盖人工修正 |

翻译采用文字 ID 回填，保留本地图片、公式、代码及样例；图片内文字不翻译，译文标记尚未人工确认。PDF/图片/ZIP 不能仅凭下载链接视为可翻译正文。上述是源码边界，不保证每道题都有译文或翻译质量已实测。

证据：[MemberProblems](../feat/web/src/views/MemberProblems.vue)、[网页筛选默认值](../feat/web/src/lib/member-problems.js)、[Problem](../feat/web/src/views/Problem.vue)、[SecondaryProcessingPanel](../feat/web/src/components/SecondaryProcessingPanel.vue)、[AdminProblemProcessing](../feat/web/src/components/AdminProblemProcessing.vue)、[正式基础题库接口](../feat/api/acm_api/backend_api.py)、[本地标签包装](../local_demo/problem_bank_labels.py)、[翻译正式集成限制](algorithm-tagging-delivery.md)、[App 题面](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MainActivity.java)、[App PDF](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/PdfActivity.java)。

### 3.5 排行榜、训练与 Wiki

| 功能 | 网页 | App | 差距与边界 |
| --- | --- | --- | --- |
| 近7/30/90日、近1年、生涯 | 有 | 有 | 已共有 |
| 五平台多选组合、总数/单平台排序、每页10/20/50/100 | 有 | 有 | 已共有；不能沿用旧文“App 只有周/月/总、固定20条” |
| 零 AC 排名 | 网页未传 `positive_only=1`，默认可显示零 AC | 过滤所选平台合计为0的成员 | 是有意保留的差异，不是统计缺失 |
| 北京时间当日榜、页码输入跳转 | 当前页面均无对应控件 | 当前页面均无对应控件 | 当日 `period=today` 后端已支持，不能记成缺 API；页码输入是客户端缺入口 |
| 本人今日训练、三档推荐、弱项、难度、挑战历史 | 有 | 有；另有活跃天数/连续训练统计 | 主流程共有；App 额外“到期补题”区域仍依赖缺失复习接口 |
| CF 赛事复盘六态 | 有 | 有：待处理/未通过/待补题/已解决/已复盘/忽略 | 当前已不是旧 App 四态，不再列六态为网页独有 |
| Wiki 分类、搜索、正文/代码/公式、公开历史、关联练习 | 有 | 有原生简版 | 主流程共有，站内关联练习可进入原生题面 |
| Wiki 章节目录锚点、阅读位置/分类路径、标签等完整阅读导航 | 有专门目录与导航区域 | 当前页面以正文和分类列表为主，无同等目录导航 | App UI/阅读体验差距，基础文章接口已存在 |
| 离线算法模板库 | 无对应产品功能 | 旧“算法模板”入口现转 Wiki，不是独立离线模板库 | 不得继续按历史需求将其计为 App 已交付能力 |

证据：[Leaderboard](../feat/web/src/views/Leaderboard.vue)、[排行参数实现](../feat/api/acm_api/forum_api.py)、[TrainingPanel](../feat/web/src/components/TrainingPanel.vue)、[ContestReviewPanel](../feat/web/src/components/ContestReviewPanel.vue)、[Wiki](../feat/web/src/views/Wiki.vue)、[App 排行/训练/复盘](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MainActivity.java)、[App Wiki/比赛进度](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/WebFeaturesActivity.java)。

## 4. 外观、本机能力与更新

| 功能 | 网页 | App | 差距与边界 |
| --- | --- | --- | --- |
| 官方主题库 | 原有设计、相变信号、天使之城、方块工坊四套实际模板 | 已打包对应原 Vue/CSS/SVG 主题层 | 原神/绝区零当前只有分类，无实际模板；两端不能虚构主题 |
| 官方样式覆盖范围 | 整个网页 DOM 可使用模板 CSS | 背景/横幅等用原资源；原生文字/按钮/列表由共享 Android 样式适配 | 不能将 App 描述为全页面逐项直接执行网页 CSS；离线资源也不会自动跟随远端更新 |
| 明暗与配色编辑 | 浅/深/跟随系统、基础/高级 token、对比度检查/修复、恢复默认 | 有主辅色、调色盘、官方浅深方案/网页配色 JSON；无同等高级编辑与对比度修复界面 | 网页编辑更细；App 当前没有同等“跟随系统”模式控件 |
| 本机相册背景、自由裁剪、纯色/渐变、透明度 | 无同等背景设置与打包流程 | 有，背景/模块/控件透明度独立 | App 本机额外能力，图片不上传业务服务器 |
| 我的主题、编辑预览、重命名/删除、完整分享导入 | 网页有本机配色收藏和 JSON 导入/导出 | App 用 `.acmtheme` 保存设置、原图和裁剪，名称/缩略图均可应用，系统分享 | 两种格式不等价：网页配色 JSON 不携带本机背景原图或完整模板代码 |
| 每日提醒时间、通知开关/权限 | 没有 Android 本地通知能力 | 有，本地填写时间和系统权限流程 | 独立提醒可用，不表示云端打卡接口已完成 |
| 启动/手动检查新版、下载/校验/系统安装、离线更新说明 | 网页无 APK 自更新产品流程 | 有，默认自动检查，下载前确认 | 当前 GitHub 单源；自站候选 #105 及服务器不在本次基线 |
| 网络缓存、重连提醒、下拉刷新、子页面动画 | 网页有各页读取/错误重试与浏览器导航 | App 有进程内缓存、10秒连接预警/重试、3秒重连成功、下拉刷新及页面栈 | 是客户端体验差异；缓存不等于跨进程全业务离线 |

证据：[网页主题目录](../feat/web/src/lib/design-template.js)、[网页配色编辑](../feat/web/src/components/ThemeEditor.vue)、[App 个性化](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/AppearanceActivity.java)、[主题采用范围](android-official-theme-adaptation-v0.2.17.md)、[主题包格式](android-theme-package-v1.md)、[App 本地提醒](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/TrainingReminder.java)、[更新页](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/UpdateActivity.java)、[修改标准](android-modification-standard.md)。

## 5. 管理员功能差距

普通账号两端均不应展示管理入口；App 每次管理读写仍由正式后端鉴权。下表只比较 admin/root 可见功能，不把“打开网页后台”算成 App 已有原生实现。

| 管理能力 | 网页 | App | 目前分工/差距 |
| --- | --- | --- | --- |
| 话题审核、查看正文、通过/退回、举报处理 | 有 | 有便捷页 | 共有，审核带内容版本；举报处理不等于删除帖子 |
| 单成员关键词/学校/身份筛选与资料查看 | 有 | 有 | 主流程共有 |
| 单成员资料、四平台 OJ 绑定维护 | 有，另有身份输入/冲突/恢复编辑等完整管理流程 | 有资料修改与绑定变更确认；QQ/校OJ不在此修改 | App 简版，不等于普通成员能自助改绑；无网页全套可恢复批量编辑 |
| 单成员改密、启停、Root角色修改 | 有 | 有 | App 对管理员账号的权限更改仍限 Root，复用服务端约束 |
| 初次开户、批量发号/选人、重发临时密码、CSV | 有 | 无原生流程，提示网页开户 | 按既定分工留 Web |
| Excel 导入、预览/校验、批次提交/取消、结果/凭据下载、开关 | 有 | 无 | 按既定分工留 Web；敏感批量凭据不宜塞入普通搜索或缓存 |
| 管理员指定成员生成训练 | 三档推荐，平台/弱项/难度、历史 | 一次生成一题，四平台有效默认难度、历史 | 都有正式接口，但功能粒度不同；不能写成完全相同 |
| 管理员指定成员六态复盘 | 有 | 有 | 主流程共有 |
| 题库数据库浏览、标签/翻译/人工处理 | 有新面板，但新二次处理路由仍为本地验收实现 | 无 | 正式后端集成和 App 适配是两项工作 |
| 初始化题库、采集统计、单场/全平台采集、刷新已有题目 | 有 | 无启动采集流程；可看既有同步任务 | 按分工留 Web，不是 App 没有任何任务功能 |
| CF 选题、成员范围、近期AC、全历史候选查重、提交证据与复制 | 有 | 无 | Web 专用；不是在线组织比赛/判题系统 |
| 同步任务查看、取消、状态和基础进度 | 有 | 有 | 主流程共有 |
| 全员定时同步任务成员数进度 | 网页已显示成员单位 | App 可显示通用 done/total | 数据可直接复用，App 单位文案可继续适配 |
| CF 目录补全阶段、失败比赛列表 | 网页新增明确阶段与失败详情 | App 只识别 metadata/一般进度及题目失败列表 | PR #109 新增响应字段尚未完整适配，现有 `/api/tasks` 可复用 |
| CF 比赛播报时间/关闭 | 有 | 有 | 共有，北京时间 HH:MM；影响全站 |
| QQBot管理员名单、全局字号等完整设置 | 有 | 无同等编辑页 | Web 角色与 Bot 名单不能混为一谈 |
| Wiki 分类管理、文章编辑/草稿/发布与版本操作 | 有 | 只读 Wiki，管理跳网页 | 按分工留 Web |

证据：[网页管理路由](../feat/web/src/router.js)、[账号管理](../feat/web/src/admin/AccountsList.vue)、[Excel导入](../feat/web/src/admin/AccountImport.vue)、[成员管理](../feat/web/src/admin/Members.vue)、[CF选题](../feat/web/src/admin/CfPractice.vue)、[题库与处理](../feat/web/src/admin/Problems.vue)、[任务进度](../feat/web/src/components/ProblemTaskProgress.vue)、[全局设置](../feat/web/src/admin/Settings.vue)、[Wiki管理](../feat/web/src/admin/Wiki.vue)、[App便捷管理](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/AdminQuickActivity.java)。

## 6. 两端都不能算完成的训练闭环

| 能力 | 网页 | App | 正式后端状态 |
| --- | --- | --- | --- |
| 教练题单、截止/下发、成员完成进度 | 当前路由没有完整题单管理 | 有题单占位页 | 未实现 `/api/club/sheets` |
| 按题讨论、WA/TLE等标签 | 只有普通论坛，不是按题聚合 | 有查询/发起入口 | 未实现 `/api/club/problem-discussions` |
| 私人错因笔记/标签 | 无专用错题本 | 有错题本表单/列表 | 未实现 `/api/me/club/mistakes`；题目收藏不能等价替代 |
| 补题计划、1/3/7天推进及到期联动 | 六态复盘已有，尚无间隔复习闭环 | 有复习入口及今日训练联动占位 | 未实现 `/api/me/club/reviews`；本地通知调度不能凭空生成云端计划 |
| 每日目标与幂等打卡 | 有基础训练/活跃数据，无该业务接口 | 有打卡界面及独立本地提醒设置 | 未实现 `/api/me/club/checkin` |
| 完整公开成员目录 | 有公开排行榜摘要，无完整目录页/接口 | 借排行榜搜索，无完整目录 | 已有公开成员资料接口不等于完整可搜索目录 |

证据：[App训练界面及占位请求](../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/ClubActivity.java)、[正式服务注册](../feat/api/app.py)、[缺失能力矩阵](android-modification-standard.md)。这些占位可能显示“无API接口”，不能拿旧需求文档或旧分支实现作为本节点的完成证明。

## 7. 后续接入顺序建议与复查方法

本节仅供选择，不代表已获准实施：

1. **先做无需新增正式后端的 App 展示适配**：原始标签精确筛选、样例说明/ZIP附件、Wiki章节导航、任务目录阶段/失败详情。默认平台差异也应先决定是否跟随网页当前“全部平台”。
2. **先完成正式后端再接 App**：题面翻译结果读取、有效中文标签/组合筛选、来源/审核状态。首轮成员端可只读已保存结果；付费执行和复杂人工审校继续留 Web。
3. **按既定分工保留差异**：OJ 自助操作暂转网页；批量发号/Excel/CF选题/复杂Wiki编辑留Web。账号注销如要加入App，先明确服务端开关与完整回执流程。
4. **缺失训练闭环另定契约**：题单、讨论、错题、间隔复习、打卡不能靠前端拼装冒充后端完成。

下次比较从本节点的 main SHA 和快照开始，分别记录网页/后端新提交、App实际版本以及本地未提交源码；比较范围不能只用最近一个 App Tag 之后的 Git diff。修改文档不移动本节点；新变化另写节点，不覆盖本次历史。

本次只做文档与指纹检查，没有修改运行代码、生成新版安装包或改变此前0.2.21候选哈希。发布、自站和PR流程保持等待状态。
