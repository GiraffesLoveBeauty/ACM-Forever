# Android 修改标准与模块关联（v1.0.0）

2026-11-24 1.0.2 候选：排名页使用独立短标题与图标筛选，统计区域按内容换行，不能通过收缩字号后继续把昵称与总数挤在同一横行。通用 `HomeBanner` 及其他页面不随排名收缩；既有筛选、搜索关键词提示、主题配色、零 AC 过滤、分页与公开主页跳转继续联查。范围见 [android-v1.0.2-compact-ranking.md（排名小屏布局）](android-v1.0.2-compact-ranking.md)。源码提请 Review，合并与发布另行确认。

## 1.0.0 发布、署名与管理员测试渠道约束

本轮为1.0.0/code45正式发布准备，恢复延期的同包名测试渠道；PR #150第二轮本地Review通过（04f35c8），已补录实际人员记录，用户授权合并与Tag发布。当前验证与上线边界见[android-v1.0.0-verification.md（本轮验收）](android-v1.0.0-verification.md)，契约见[android-v1.0.0-release-channels.md（双渠道）](android-v1.0.0-release-channels.md)；实际公开状态以Release及后续验收为准。

- 关于页、当前/历史版本共用`credits.json`。每轮分别核对源码提交者、Review发起者、实际Review者、自动发布者；保留真实GitHub用户名与头像。0.2.21及以前保留原历史人员；0.2.22起已完成版本按用户确认记录`MiaoJJ13445`。不得把上一版人员错误沿用为本轮已完成证据。
- 发布前必须完成 **实现与测试 → 提PR → 当前head的真实Review → 修复后重新Review → 补录完成记录并核对该差异 → 授权合并 → Tag构建**。`development`保留空评审；真实Review后改为`reviewed`，填写PR/证据与人员但不预填发布者。发布快照可保持`reviewed`，下轮据实际Release补为`published`。不能使每个已发APK仍将自身标为永久“待Review”。
- `release_credits.py`在Tag源校验、清单生成及正式/测试附件发布前拦截缺失记录；核对APK内快照与已评审源码。不得在CI中推断评审者、修改已签APK或用测试夹具冒充真实Review。候选本地可构建、验收，但未收录实际Review时正式Tag必须失败。
- 正式与测试均同包名、同固定签名、`debuggable=false`，复用数据；测试沿用当前线上普通包code，正式使用更高code。测试修订独立递增；普通与测试APK互不内嵌。测试包禁止自动检查，仅手动选正式/管理员测试渠道。
- 正式公开清单schema2/distribution=release且无旧`channel`字段，兼容旧0.x的debug渠道检查。默认Gitee优先、GitHub兜底；Gitee仍由维护者手动同步同一套八附件。测试草稿永不公开、永不镜像Gitee、不影响公开latest。
- 测试主包和四模块均经`/api/admin/android/releases/*`鉴权，不使用可匿名下载的测试URL。匿名/成员/首次改密、角色变化、退出/换号、取消和进程恢复均须覆盖；服务器Token不进入APK、清单、日志或客户端跳转。
- 测试安装会话必须持久保存控制器归属，不能将私有回执统一发给普通`updates()`。真实携带split的安装须验证系统确认、取消和失败；旧私有控制器凭据在退出/换号/进程重建后失效。
- 同code的普通模块和不同previewTag必须隔离清单、归档与解包目录；离线私有记录只允许完整性验证，不携带会话或授权下载。健康恢复、复用回执、更新暂存及显式删除须共同适配该归属；未来测试修订不能提前启用。回归必须使用内容变化的真实签名资源，并保留旧普通清单，不能仅以未变资源复用代表兼容验收。
- 恢复延期实现时以当前main三方合入，不能覆盖0.2.24之后的模块编号、健康恢复、04:00检查日、请求调度、Gitee回退与草稿归属修复。真实旧包→测试→旧包→正式须保留账号、Keystore密文、主题、历史、私有文件及可选模块。只测基础包不足以验收模块兼容。
- 新后端属于`feat/**`，合并会触发既有自动部署；必须在合并前由运维确认草稿读取配置与回退方式。未配置时应真实返回503，不影响公共正式更新与其他业务。

## 0.2.30 连接与训练维护约束

0.2.30行为见 [android-v0.2.30-network-training.md（弱网与题单排名）](android-v0.2.30-network-training.md)，已通过PR #145合入并发布；原文保留当时验收阶段。页面读取统一使用 `PageReads` 与 `ReadRequests`；缓存回放、JSON 读取、写入分开调度。普通读取最多并发两条，同源同会话同路径可合并；切页取消该页订阅，回调仍须核对页面及会话代次。UI 禁止获取跨越网络请求的锁，`ApiClient.stateLock` 只用于短时状态，写事务 monitor 不得在主线程获取。

新写入口必须在排队前捕获会话，并在后台通过 `ApiClient.bind(owner)` 绑定；页面离开不重放、不随读取取消写操作。更新 `ReadInvalidation` 关联表，不能恢复“每次写入清空所有缓存”。管理员、认证和注销读取不缓存；HTTP 条件缓存只允许白名单公开接口，遵循服务器 `no-store`。草稿防抖 2 秒，提交前立即 flush；不得阻塞返回，也不能让迟到结果清除新编辑内容。

提交审核期间离开并重新进入编辑器时，旧请求成功后的同代草稿清空必须同步当前编辑控件，不能只清模型后留下禁用的旧输入框。新草稿代次或新输入不得被清除。OJ绑定变化会清除平台提交证据、结束随机挑战，关联失效表须覆盖题目列表/详情/比赛进度、训练摘要/挑战、弱项统计、训练任务及个人资料/公开统计；验证成功写入后立即离线时旧证据不能回放，论坛、Wiki和草稿仍应保留。回归入口为`composersubmit`与`networkreads`。

图片读取、压缩或上传结束后，先解除当前发布页因`composeBusy`产生的控件禁用，再处理成功、失败及归属变化分支；不能只恢复布尔状态。恢复不能重建输入框或重置正文/光标，不得强制跳回编辑页。图片插入仍同时校验会话、草稿代次、当前输入框和页面；旧结果不能写入新草稿。回归入口`composerimage-success`、`composerimage-failure`须覆盖上传中离开/返回、切换草稿、停留其他页面、原编辑器内成功/失败及每次选择仅上传一次。

`PageRefresh` 在 Activity 隐藏时 pause、可见时 resume，连接失败退避 10/20/40/60 秒（带偏移），网络变化提前重试；不能对无接口/权限错误重复请求。10 秒红框和成功 3 秒提示保持。题单排名默认 none，由后端对筛选全体计算后分页；旧服务器未确认 order 时必须提示，不得客户端只排当前页。后端变更的部署确认与回退约束见本轮说明。

## 每轮修改与发布的必做同步

以下五项为已发布0.2.29的维护约束；见[交互、更新日与模块管理说明](android-v0.2.29-maintenance-followup.md)。修改以下关联时，源码、验证及说明须在同一PR交付，不能只改页面文案：

1. **密码统一控件**：运行中的所有密码输入，以及管理员生成的临时密码，都通过`PasswordFields`提供普通眼睛显隐；默认隐藏，切换保留光标。改密的当前/新/确认、重置、OJ确认、注销均检查；不将密码或显隐状态写入实例状态，不因切换可见而改变提交值。历史排除的管理壳不作为验收入口。
2. **发帖内嵌预览**：`ComposerPreview`与当前编辑器共存，默认下方、可切右侧，左上关闭、右上切换。布局变化不能替换编辑器、丢光标或切换草稿归属；继续复用清洗后的`ContentView`，禁止原生JS桥。正文修改后预览同步，切换/关闭销毁旧阅读器；转屏和返回保存布局状态。
3. **自动检查日**：`UpdateCheckDay`以手机当前时区、本地04:00划日，不是UTC日或固定24小时。默认开启；登录后每天最多主动尝试一次，即使失败也不在当天自动重试。任意手动/自动检查成功均阻止当天再次主动检查。主动尝试在发起前持久记录，进程重建不重置。手动检查和进入更新页仍立即检查；关闭开关、改变源、升级App不能绕过当天记录。没有后台定时唤醒；下次启动/回到主页时按当前日判断。
4. **特别鸣谢与版本日志**：每轮核对公开贡献者、新增参与者及头像摘要，核实上一版PR/Review/Release后同步`credits.json`与`history.json`，关于页及更新页共用快照。0.2.22起已完成的Review按维护者2026-11-15的确认署名为`MiaoJJ13445`；产品界面与版本记录必须使用明确GitHub用户名，不能使用“本人”等依赖阅读者身份的代词。新候选未完成的评审、发布必须留空。核对上传、发起Review、实际Review、自动发布四类职责，保留证据与历史人员，不把机器人无意见或维护者署名写成GitHub人工APPROVED。版本号/code、当前日志、鸣谢版本键三者一致。
5. **模块编号与下载**：稳定ID/文件名不能改成展示编号；展示`number`使用完整拼音与声调-App版本-标准大写罗马数字（如`guan_1_fang_1_zhu_3_ti_2_ku_4-0.2.29-I`）。`revision`只按真实内容判定更新，编号或App版本变化不能让未变资源重复下载；原生包须匹配主包code与证书。旧清单字段可缺，不能伪造旧编号。基础包、四模块、两份JSON与校验文件共八附件必须完整核验；已发布Tag/附件不可覆盖。
6. **模块管理与恢复**：`StorageActivity → ModuleManagerActivity`提供主动下载和删除。清临时文件/普通升级不删除模块，显式删除才清除该ID全部版本的下载与解压副本，并移出随App更新集合；保留凭据、私人主题与原图。原生split须经`PackageInstaller.removeSplit`及系统确认，成功后再清本地文件；取消/失败不当作删除成功。回执跨进程保留，启动后台健康检查与模块管理页均恢复清理；更新摘要和实际安装统一使用`ModuleStore.updateSelection()`，有卸载回执且PackageManager确认split不存在时，即使本地清理未完成也排除该ID。查询失败不得视为卸载成功，仍安装或仅下载未卸载的模块保留。库存仍展示待清理记录，不能靠隐藏库存冒充清理完成。模块作业与App安装互斥；清理与本地恢复共用锁序。普通成员不获得管理模块下载/打开入口，但可删除本机已保留的管理模块。

论坛增量分页成功渲染时须移除独立读取错误区域，再清空引用；保留列表容器、已加载帖子与阅读位置。覆盖无缓存首屏成功、后续分页超时、重试成功，不能只验证缓存命中时的恢复。

原生模块的主动删除判定、卸载回执恢复、更新选择及`ModuleStore.removeLocal()`删除前保护，必须使用`installedNativeChecked()`严格查询。只读可用性使用的空集合回退不能用于破坏性操作；查询异常应保留各版本归档、已下载记录和持久回执，不发布删除成功。异步清理执行时仍须重新查询，不能只信任调度前快照或系统成功回调；恢复查询后仍安装的split继续保留，明确不存在时才恢复清理。

提交前核对密码全入口、预览/草稿重建、04:00/时区/失败/手动成功抑制、显式关闭、模块选择性删除/取消/恢复及未变内容复用；相关回归见本轮说明。测试通过只说明已执行范围，不替代当前head的Review、真机验收或发布授权。

0.2.29/code43涉及管理员全部题单、论坛两条增量加载、首屏刷新、更新诊断与可读模块编号，见[该版行为与验证](android-v0.2.29-lists-updates.md)。以下版本段落保留历史实施背景，以文首1.0.0约束和实际源码为准。

本轮0.2.28/code42接入正式训练任务、练习总览和模块独立编号/恢复，详见[实施与验收说明](android-v0.2.28-practice-recovery.md)。题单就是管理员下发的training task，不再请求`/api/club/sheets`；旧打卡提交已移除，提醒本地保留。管理写操作绑定读取时账号/任务版本；发布幂等键与预览配对，禁止通用自动写重试。

0.2.27/code41更新源改为Gitee优先、GitHub兜底，详见[源选择与发布配置](android-v0.2.27-gitee-updates.md)。`UpdateSources`控制正式Release解析和清单兜底；`UpdateManifest.downloadUrls`仅为固定Gitee仓库添加同版本GitHub备选；`ModuleSpec/ModuleNetwork`控制固定仓库的同版本模块和CDN白名单。自定义清单不能被静默替换。不可删除原APK/模块的哈希、版本、签名校验，或在校验失败时直接安装。`gitee_release.py`只允许匹配源码Tag的Actions运行，Secret仅发布端使用；八附件匿名回读后才解除预发布状态，PATCH 必须携带原 `tag_name/name/body`。GitHub 已公开而 Gitee 未完成时，重跑须先核对真实 Tag/commit、源码版本、渠道和固定证书，再下载校验原始八附件；成功恢复后跳过构建和 GitHub 发布，不允许用重新打包的不同字节覆盖首发文件。1.0.0和自站PR继续独立保留。

上一公开版本0.2.26/code40的论坛、主题返回和搜索拖动修复见[实施记录](android-v0.2.26-reader-and-theme-return.md)。Markdown公式须在解析前保留原文，不能全局替换代码块或二次扫描转义货币；共享阅读器变更须联查论坛、预览、Wiki和题面。高级个性化的页面位置须随页面及Activity状态保存，首次恢复不能被onResume的重复渲染覆盖。以下0.2.25段落保留模块实施时的记录。

首页及我的空间话题卡片统一用`ForumExcerpt`执行网页`postExcerpt`的文字摘要规则，最多三行，末尾省略；不要直接显示原始`excerpt`，也不要为摘要逐卡增加WebView。0.2.26搜索拖动边缘滚动上限为192dp/秒，旧版96是历史值；调整时须联查帧率无关性、掉帧限速、反向/离开即停以及列表边界。

本轮可选模块实现与维护约束见 [android-v0.2.25-optional-modules.md](android-v0.2.25-optional-modules.md)。原生高级设置与便捷管理现位于 `app/advanced/`、`app/admin/`；共用 Provider 留在基础包。不得向基础 DEX 再引入 feature Activity 的 class 字面量，应经 `OptionalModules` 按实际已安装 split 放行。资源在 `module-resources/`，使用已签名的同版本制品，不是下载标记解锁。`ModuleStore` 的持久目录与已下载记录不可随清缓存或普通升级删除；默认随 App 更新已下载模块，开关在检查更新页。

历史：0.2.25/code39开发时曾延期1.0.0；当前已恢复实施，以文首为准。题面专用样式由`ContentView.problem`与`reader/`控制，不修改论坛/评论/Wiki样式；`ProblemSummary`解析真实难度、数组或历史文本标签，`ProblemBadges`在题库、详情及比赛进度统一换行展示。比赛进度复用现有接口的`tags: string[]`加法字段；旧服务器缺失时提示“算法标签未提供”，不能逐题抓详情或猜测标签。后端变更需与App联调，详见[0.2.24说明](android-v0.2.24-problem-reading.md)。

0.2.25当时只包含可选模块与八附件发布事务，延期双渠道另留本地。本次1.0.0已恢复客户端、管理员安装包API和workflow，且与当前模块机制联调，不能再以该历史分离记录判断当前提交范围。

状态：1.0.0本地源码候选，待Review，2026-11-16。以实际代码与测试结果为准。适用工程 `Android_APP/app/`，不改变仓库协作规范。维护责任、人员署名、修改步骤和发布交接另见[App 修改与维护交接规范](android-maintainer-handover.md)。

## 目录与修改入口

基础包 Java 路径前缀为 `Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/`。高级设置类在 `Android_APP/app/advanced/src/main/java/com/giraffeslovebeauty/acmforever/`，便捷管理 Activity 在 `Android_APP/app/admin/src/main/java/com/giraffeslovebeauty/acmforever/`；共用安全与数据辅助类仍在基础包。

| 入口 | 职责 | 修改时必须联查 |
| --- | --- | --- |
| `AcmApplication`、`ApiClient`、`SessionVault` | 进程共享会话、CSRF、权限、缓存和加密凭据 | 退出、切账号/服务、Activity 重建、禁止主线程等待网络锁 |
| `LoginGate`、`MainActivity`与`AppUpdates` | 未登录 UI 门禁及会话失效回登录 | 未登录只显示登录表单；唯一例外是已有本机注销回执查询。隐藏顶栏/底栏/设置，内部子页启动或恢复不能旁路；登录前不显示更新弹窗，不能将客户端门禁当成后端鉴权 |
| `GithubCredits`、`CreditsViews`、`AboutActivity`、`UpdateActivity`与`assets/releases/credits.json` | 版本负责人、评审协作、特别鸣谢与离线头像 | 主体与自动化职责分开，来源链接和快照日期保留；早期汇总评审注明范围，当前未完成评审留空；名单、头像、版本日志同步验证，维护交接见独立规范 |
| `MainActivity`、`NavigationStack`、`PageMotion` | 首页/排名/题库/发帖/个人中心/账号设置及原生详情 | 五个平行栏目无动画，子页面右入/右出；临时快照取消与释放，`external_navigation`、详情返回、草稿归属、搜索入口防重 |
| `SearchActivity`、`SearchModules`、`SearchHotPosts` | 搜索顶栏、首次聚焦、热搜、结果、模块设置和历史记录 | 热搜仅首批30条热门候选，按真实阅读量选至多4条；异步返回不抢输入焦点，搜索设置入口唯一，公开 ID、本人接口范围、缓存及模块独立失败 |
| `ModuleOrderView`、`ModuleDragPhysics`、`ModuleEdgeScroll` | 整卡纵向拖拽、90%缩放、边框提前让位、逐项弹簧传播与慢速边缘滚动 | 所有行均受列表上下边界约束，不能只限制选中行；开启列表裁剪；边缘速度按经过时间及密度计算，不能按每帧固定距离；原始行身份不等于bringToFront后的绘制次序；首个拦截事件、取消不保存、松手保存、无障碍及父滚动拦截继续联查 |
| `ModalDialogs`、`KeyboardInputs`、窗口样式 | 普通弹窗/全屏表单和软键盘 | 自定义全屏Dialog安装编辑器后清除阻挡IME的窗口标志；仅搜索入口主动显示，普通表单点击唤起；不绕过权限/防重 |
| `MobilePageActivity`、`PullRefreshLayout`、`PageRefresh` | 搜索与便捷管理的页面壳、缓存读取、串行后台操作 | 页面代次、会话代次、槽位绑定；缓存展示不能启动下一轮轮询，使用仅在有效网络响应展示并结束后执行的回调；下拉只重复注册的读取，排序长按不能被父滚动抢占，不得刷新草稿或重放写操作 |
| `AdminQuickActivity`、`AdminApiPolicy`、`AdminMemberEdits` | 手机便捷管理和 API 白名单 | 服务端角色重验证、CSRF、审核版本、敏感内容禁止通用缓存 |
| `SyncTaskResult` | 同步任务的数值结果展示 | `-1`也可能是已有成员抓取失败，显示通用“同步失败”；不能据此推断成员不存在。新增条数与未绑定/抓取异常/暂停/洛谷访问受限停用仍各自展示；`-6`只表示该成员洛谷账号被单独停用，不得把它解释为全局洛谷暂停 |
| `ChallengeDifficulty` | 管理员单题训练的难度选项和默认值 | 与 `acm_api/difficulty.py` 的有效值及网页训练默认值一致；切换平台同步难度，空选项不得发送请求 |
| `WebFeaturesActivity` | 通知/投稿进度/比赛进度/Wiki | Wiki 站内练习相对链接进入原生题面，外链 HTTPS 校验 |
| `WikiCatalog`、`WikiOutline`、`WikiReaderNavigation`、`ContentView`及`reader/content.js` | Wiki分类路径、文章标签、章节目录/高亮与阅读位置 | 只读公开接口；分类和文章独立失败；从清理后的实际DOM取标题，代码块不算目录、重复标题ID唯一；无JS应用桥，章内偏移/历史版本/转屏/返回及动态布局必须联查 |
| `ProblemTags`、`ProblemTagPicker`、题库与搜索/比赛进度 | 原始标签候选搜索、完整标签精确筛选 | `tag`关键词与`problem_tag`完整标签分开编码；真实候选、平台切换清标签、筛选归第一页、翻页/返回/重建保留、单窗防重及会话代次 |
| `OjBindingsActivity`、`OjBindingState` | 本人 OJ 绑定列表、归属核验、绑定/改绑/解绑与同步 | 复用 `/api/me/profile` 的 `bindings` 能力；是否绑定取账号字段而非 AC 数；确认请求必须核对实际输入与验证码所属账号；密码/确认不持久化，写入不自动重试，返回个人中心/账号页刷新 |
| `AccountClosureActivity`、`AccountClosureFlow`、`AccountClosure`、`SessionVault`及`MainActivity`登录页 | 本人账户注销、实时开关、确认和结果回执 | 独立加密回执先保存再提交；未登录时仍须有本机回执查询入口；当前密码不持久化；管理员不能提交；转屏/断网/重启只查询，不重放POST；已明确的提交前拒绝可清回执，查询限流不得清理；必须匹配回执与提交时间才报成功，同QQ新代账号不可被旧回执退出 |
| `TrainingTasksActivity`、`TrainingUi`、`ClubActivity`、`TrainingReminder` | 正式题单/安排，讨论、错题、复习占位和本地提醒 | 任务证据与待核验分开；网络请求完成后才安排下一轮，已有读写请求时不重绘使其代次失效；缓存/网络双次展示和子页返回均保留当前滚动位置；停止后台页轮询，通知设置不丢 |
| `CloudDrafts` 与主页面编辑器 | 云端多草稿和自动保存 | 账号+草稿代次；切换草稿、返回旧页、迟到写入、Markdown 导入归属 |
| `PdfActivity`、`ContentView`、阅读器资源 | PDF、Markdown/公式/代码与图片 | 缩放/翻页/复制、受限媒体地址、缓存边界 |
| `ImagePreviewActivity`、`PageRefresh`、`ApiClient.MediaFormatException` | 图片失败后的原页手动/自动恢复 | 仅连接失败重试；格式/尺寸/权限错误不循环；十秒预警、关闭仍重试、成功三秒消失、会话代次与退出取消 |
| `StorageActivity`、`ModuleManagerActivity`、`TemporaryStorage`、`PdfFiles`、`HelpActivity`、`AppUpdates` | 缓存、临时文件、模块及安装包四块存储管理，本机帮助说明 | 文件操作在后台；目录读取失败不能算作零占用或清理成功；主动清理PDF失败时保留索引供重试并报告错误，退出时仍丢弃全部索引访问；保留凭据、主题、草稿、活动PDF与近期分享；模块仅主动选择才删除，安装包单独清理，下载/校验/安装期间拒绝；新页面继续强制登录 |
| `AppAppearance`、`MobileStyle`、`ProfileCover`、`LocalThemes` | 主题、主辅色、全屏背景、模块/控件透明度 | 深浅色、状态栏、原位变色、保存/预览/删除本机主题 |
| `ThemePackage`、`LocalThemes`、`ProfileCover` | `.acmtheme`格式、隔离安装、原图字节与非破坏性裁剪 | [格式规范](android-theme-package-v1.md)；布尔选项、主辅色/透明度、模板浅深配色、原图及裁剪同时往返；文件I/O不在主线程，先校验后登记，导入不覆盖当前外观 |
| `ThemeShareProvider`（基础包）、`AdvancedAppearanceActivity`（高级模块） | 后台生成私人主题文件并调用系统分享 | 独立只读附件、ClipData读取授权、随机文件名与缓存回收；不共用APK Provider，不包含账号字段，不自动发送QQ/微信消息 |
| `OfficialThemeView`、`theme-renderer/` | 原Vue/CSS/SVG离线主题层，无原生JS桥 | [源文件关联](android-official-theme-adaptation-v0.2.17.md)；原源变化重跑构建工具和指纹检查，禁止用重新描摹替代；原生控件仍使用共享样式 |
| `AppUpdates`、`UpdateManifest`、更新页面与 Provider | 检查、下载、校验及系统安装 | Gitee优先/GitHub兜底与自定义源、取消/重建/进程恢复、包名版本签名、更新日志 |
| `tools/create_update_manifest.py`、`tag_release.py` | 同一 APK 的清单和GitHub Release事务 | `.github/workflows/android-release.yml`、签名渠道、不可变目录和 latest |
| `OptionalModules`、`ModuleDownloads`、`ModuleStore`、`ModuleUpdates`、`ModuleInstaller` | 按需下载、真实系统安装及升级保留 | 登录/管理员和账号代次、索引版本、签名叶证书、大小/哈希、分包版本、未来资源隔离、取消和旧目录保留；不得按偏好标记判定已安装原生功能 |
| `tools/create_module_assets.py`、`module-resources/`、`app/advanced/`、`app/admin/` | 四模块制品、资源源文件与真实拆包 | 与基础APK同版本和证书；八附件必须全部回读通过才能公开，不把模块包或密钥提交源码库 |

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

本轮按 main `52d28788` 更新题单/安排状态；其他项沿用原核查，不是服务器部署证明。其余缺失能力保留第二优先级，本轮不新增业务后端。

| 能力 | App 既有占位路径 | 网页已有基础 / 尚缺部分 |
| --- | --- | --- |
| 社团题单 | 已接入 `/api/me/training-tasks`，不再缺列表/详情接口 | 管理员下发、截止、完成进度及同步已在当前main实现；仍缺全量关键词搜索契约 |
| 按题讨论 | `GET/POST /api/club/problem-discussions` | Web 有泛论坛、评论、审核、举报；尚缺平台+题号关联与讨论标签检索 |
| 私人错题本 | `GET/PUT/DELETE /api/me/club/mistakes` | Web 有收藏；尚缺私人错因笔记/标签。退休笔记接口不能代替 |
| 间隔补题复习 | `GET/PUT /api/me/club/reviews` | Web 有赛事六态；尚缺复习阶段、到期和1/3/7天推进 |
| 每日目标与打卡 | 本轮移除旧打卡提交和该占位请求 | 入口改为“训练安排”，使用正式任务摘要；通知及时间继续本地保存 |
| 完整公开成员搜索 | 暂复用公开排行榜 | Web/移动已有公开ID、资料和已发布话题；完整成员目录超出现有搜索范围 |

除已替换的题单/打卡外，表中的 `/club/` 路径仍是客户端已有约定，当前仓库尚无对应后端路由；后续需先确定契约，不能把界面存在当作API已实现。本轮搜索还需要对应的关键词/分页契约。

更新分发使用Gitee公开Release的JSON/APK并保留GitHub兜底，不需要业务 `/api/mobile/v1/releases/*`；自站客户端与镜像已从本PR拆分，另待配置和review。相册背景、裁剪、主辅色、透明度、本机主题、搜索设置/历史、通知时间均本机保存，不需要上传接口。公开成员ID/平台题数/已发布话题已有移动接口，不再列为缺失；本人OJ绑定的新本地实现见下节，不改变服务器已开放的平台范围。

## 本人 OJ 绑定（本地新增，2026-11-06）

个人中心的单平台通过题数卡在本人未绑定时显示“绑定”，替代题数位置；已绑定且零AC显示0，不显示绑定按钮；ALL与他人主页不展示操作。账号设置 → 个人资料 → OJ账号绑定进入原生列表，已绑定展示用户名和“修改”，未绑定展示“绑定”。

状态来自 `GET /api/me/profile` 的 `user` 与 `bindings`；不凭平台名称假定服务可用。绑定详情复用 `POST /api/me/bindings/{platform}/verification`、`confirm`、`sync` 和 `DELETE /api/me/bindings/{platform}`。同步状态可能为 `disabled`：表示洛谷公开练习页返回 HTTP 403，保留已有记录但不再自动请求，管理员重新开启后才恢复；客户端应展示服务端 `message`，不要把它当成全局暂停。当前正式后端仅CF的 `self_service=true`，其他平台说明联系管理员；已绑定平台仍可按既有接口解绑和同步。旧服务没有 `bindings` 时只读账号，并说明缺少接口。

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

管理员社团题单 XCPC 计分板的姓名、逐题首次 AC 与罚时展示见 [android-xcpc-scoreboard.md（题单计分板与时间口径）](android-xcpc-scoreboard.md)。真实姓名仅来自管理员响应；点题使用当前已加载证据，不追加网络读取。累计罚时采用服务器字段，缺失不能默认为零；接口没有错误提交次数时不得伪造标准错题罚时，也不得在当前分页内重新排序名次。

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

当前GitHub发布配置见 [Tag发布](android-tag-release-v0.2.14.md)。v0.2.27 的客户端保持 Gitee 优先；发布工作流默认 `GITEE_MIRROR_MODE=manual`，GitHub 正常发包，Gitee 由用户手动同步同批附件。只有设为 `automatic` 才要求发布凭据并运行自动镜像；不得把发布方式选择误改成 App 更新源优先级。自站更新另开PR；原讨论保留在 [PR #100](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/100)。

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
## 0.2.29 补充约束

- 管理员全部题单走现有管理API，读取前重新核实角色；普通成员和训练安排不得切到全量接口，全部题单详情不得触发本人进度刷新写入。
- 论坛分页每批2条；缓存和网络响应按页替换、按帖子ID去重。新增分页不得累积重连请求，返回保留已加载范围与阅读位置。题库和榜单仍完整加载第一页。
- 模块 `number` 是拼音声调-App版本-罗马数字的可读编号；不得取代稳定模块ID、独立内容 `revision`、摘要、签名或原生分包版本约束。旧清单兼容，内容未变的资源包继续本机复用。
- 0.2.22起已完成历史版本的本人Review署名为 MiaoJJ13445，来源为本人确认；不等于GitHub人工APPROVED，未来候选不得预填已Review。详细边界见 [android-v0.2.29-lists-updates.md（本轮行为与验证）](android-v0.2.29-lists-updates.md)。
