# Android App 完整度检查 v0.2.22

检查日期：2026-11-07。状态：v0.2.22 检查时的记录与建议；检查完成时未改业务代码或发布。随后按维护者取舍实施的 v0.2.23 改动见[修改记录](android-recovery-storage-help-local-2026-11-07.md)，其余项目见[后期计划](android-follow-up-plan-2026-11-07.md)。

## 检查节点与范围

本次以已发布 **v0.2.22 / versionCode 36** 为基准，Tag 对应提交为 `3b73bb60c60f7c7c5b9fcd5b4e54e8b7a740d371`；与 PR #111 最终提交 `237bda8644a0c723456d43a67a2e79f68a8fba36` 的 Android 源码一致。

- [公开 Release](https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/tag/v0.2.22)。本机回下载 APK 的 SHA-256 为 `c658e7212ddd396073170a3aa5f008c87ef0aff01fc972bb3dbe9d02f3186fd2`，本轮重新计算一致。
- 检查真实原生工程 `Android_APP/app/`、Manifest、发布工具、现有测试与发布日志；不把历史浏览器原型或被构建排除的管理壳算进现有 App。
- 本轮不新增测试或进行全量真机操作；已有测试结果只作为既有验证记录，不表述为本轮重新通过。
- **缺少 API 的能力全部排除**。本清单中的客户端功能可本机实现，或复用已有接口；发布可靠性属于工具链问题。
- 不改写此前冻结的网页/App 对比节点。本报告检查的是 App 完整度，不是新版网页差异清单。

## 结论

当前已经具备主要业务流程，仍处在 **0.2.x debug 迭代与验收阶段**。主要差距是故障恢复、用户说明、系统集成和验证覆盖；不能因为没有加更多业务页面，就认定功能不完整。

下面分别列出已确认的问题、可以补齐的产品入口、体验增强和验收缺口。“未实现某个增强”不等于现有流程故障；静态发现也不等于真机已经复现。

## 一、优先处理的已有问题

### A1. Tag 发布仍有首次失败的问题

**状态：实际发生过，最终发布成功，流程尚未修复。**

v0.2.22 的首次 Actions 发布在创建草稿后的上传前检查失败，报错为 `Only an unpublished draft may receive or replace assets`。确认唯一空草稿、源码与 Tag 不变后，重跑同一 Tag 才成功。v0.2.21 也有同类记录。

当前 [tag_release.py][release-script] 的 `create()` 建草稿后，`upload()` 会重新按 Tag 查询草稿；虽然已有列表查询兜底，实际发布仍出现查询结果不满足条件的情况。日志不足以独立证明全部根因，不能直接归结为某个固定 GitHub 延迟。

建议补齐：保留创建结果的 Release ID、针对新建草稿的有限重试、超时后的明确恢复说明，以及“创建成功但暂时查不到”的测试。继续保留附件回读、摘要校验和禁止覆盖已公开 Release 的约束。

验收：新 Tag 首次运行能完整发布；模拟短暂查不到草稿时可恢复；真正权限错误、重名草稿或已公开版本仍安全停止。

证据：[v0.2.22 首次运行](https://github.com/GiraffesLoveBeauty/ACM-Forever/actions/runs/42272403579/attempts/1)、[发布脚本][release-script]。这是发布可靠性问题，不表示当前已下载的 APK 损坏。

### A2. 图片预览失败后，缺少原页重试与统一连接反馈

**状态：源码确认缺少处理入口；本轮未进行真机断网复现。**

[ImagePreviewActivity][image-viewer] 已支持图片放大和拖动，但读取失败后只改变状态文字和错误模块，没有“重试”按钮，也未接入普通数据页面使用的 `PageRefresh`。用户需要返回正文重新点图，缺少页面内恢复操作；等待期间也没有同一套十秒连接失败提醒。

建议接入公共读取状态和重试机制，保留成功图片，按错误类型区分网络问题与图片格式/尺寸不支持。持续重连仅用于可重试的读取，不能把格式错误变成无限循环。

验收：图片打开时断网，页面给出连接反馈；恢复联网后可在原页重新显示图片；不重复叠加弹窗。

### A3. 发布后的“当前状态”文字需要收尾

**状态：存在已发布版本与构建时快照的文案差异，不是评审记录丢失。**

v0.2.22 内置人员记录仍是 `development`，[GithubCredits.publication()][github-credits] 会显示“当前开发版本 · 待评审与发布”；内置更新说明也保留开发阶段描述。根 README 与部分入口文档还写“待评审”。

这是先打包、后评审发布的快照机制所致。[维护规范][handover] 已要求未知评审留空、下一版补录，不能为了消除这段文字而移动已发布 Tag、替换 APK 或提前伪填人员。

建议将 App 文案改为“截至快照日期的记录；后续评审和发布信息见来源”，避免静态快照判断安装版本仍未发布。下一版补录 v0.2.22 的真实记录；仓库当前状态入口按实际发布结果更新，历史阶段记录保留。

验收：离线也能理解名单有时间边界；不把机器人评审写成人工批准，也不把已发布安装包描述成当前仍待发布。

## 二、完整产品可以补齐的入口

| 编号 | 当前缺项 | 已有基础与建议 | 优先顺序 |
| --- | --- | --- | --- |
| B1 | 用户帮助与反馈入口 | 账号设置和关于页尚无统一帮助/反馈。加入首次使用、OJ 核验、投稿审核、通知权限和更新失败的简短说明；反馈可先打开 GitHub Issue 或系统分享，不必新建反馈 API | 建议下一轮 |
| B2 | 面向用户的数据与权限说明 | 已有密码加密、禁止备份、注销后果提示，但缺少统一页面说明账号密码、搜索历史、本机主题/图片、通知和安装权限如何使用与清除。可作为“关于”中的离线说明 | 建议下一轮 |
| B3 | 本地存储管理入口 | 内容有进程缓存，PDF 和更新文件已有部分自动清理，但用户看不到占用、不能主动清理临时文件。可增加“存储与缓存”，分别展示临时缓存、已下载安装包和本机主题，避免“清缓存”顺带删除密码、主题或未保存草稿 | 建议下一轮 |

B1 可带一份用户主动生成的诊断文本：版本、Android 版本、操作页面和错误类型即可；不需要引入第三方崩溃统计 SDK。导出内容不包含密码、Cookie、CSRF、管理员成员资料或私有正文。当前没有这样的导出入口，因此用户反馈问题仍较依赖截图与口述。

依据：[账号设置 MainActivity][main-activity]、[AboutActivity][about]、[ResponseCache][response-cache]、[PdfFiles][pdf-files]、[AppUpdates][app-updates]。上述是客户端入口缺项，不意味着现有缓存完全不清理或密码以明文保存。

## 三、已有功能的可选体验增强

| 编号 | 目前能做到 | 距离更完整体验还可补什么 | 定性 |
| --- | --- | --- | --- |
| C1 | App 内能读帖子、原生题面、Wiki，能向 QQ/微信等系统目标分享本机主题 | 为帖子/题目/Wiki 增加“分享链接/复制链接”；让受支持的站内 HTTPS 链接从系统打开到对应 App 页面。未登录先登录，再恢复目标 | 可选系统集成，不是现有返回栈故障 |
| C2 | `.acmtheme` 可从个性化设置选择导入，也能生成文件分享 | 点击外部收到的主题文件时可由系统交给 App 导入；仍需复用现有文件体积、条目与原图校验 | 可选，现有手动导入与分享已可用 |
| C3 | PDF 有上一页、下一页、缩放、适应宽度；转屏会保留当前页和倍率 | 长题面可补输入页码跳转、双指缩放、关闭再打开的阅读进度。缩略图属于更后续增强 | 可选阅读便利性，基础 PDF 功能不缺 |
| C4 | 图片可单张放大、拖动 | 可补保存原图、系统分享和同一正文多图连续浏览 | 可选；原页失败恢复已单列 A2 |

依据：[Manifest][manifest] 目前只有桌面启动入口，没有站内链接或接收主题文件的 Intent Filter；[MainActivity][main-activity]、[WebFeaturesActivity][web-features] 中未见帖子/题目/Wiki 的系统分享入口；[ThemeShareProvider][theme-share] 已有主题分享；[PdfActivity][pdf-viewer]、[ImagePreviewActivity][image-viewer] 是当前阅读器实现。

这些功能均不需要新增业务 API。链接打开仍需要准确的路由映射和登录校验；外部打开入口不能放宽为任意页面或任意文件执行。

## 四、工程与验收还缺的闭环

### D1. 自动化还未覆盖 Android 设备运行矩阵

已有 [Android CI][android-ci] 会运行发布相关 Python 测试、主题资源检查、JVM 单元测试、Lint 和 APK 构建，**不是没有 CI/CD**。但 CI 没有自动启动模拟器运行仪器测试，也没有 minSdk 26 至 targetSdk 35 的运行矩阵。

v0.2.22 既有记录包括 171 项 JVM 测试、40 项发布/署名 Python 测试、2 项主题资源检查、Lint 零错误，以及 API 35 模拟器的 `accountclosure`、`creditslogin`、`startupupdates` 三组回归。这些不能代替全部手机、全部业务流程验收。

建议先把上述关键仪器回归纳入 CI，再增加 Android 8/API 26 和一个中间版本的关键流程验证。真机覆盖至少包括：

- 旧版直接覆盖安装，账号选项/主题保留，版本与证书连续。
- 未登录、会话失效、注销回执恢复、管理员/普通成员权限边界。
- 转屏、后台回收、文件选择返回、草稿自动保存与账号切换。
- 断网/慢网/重连、写失败保留输入且不自动重复提交。
- Android 13+ 通知权限、系统安装授权和主流厂商后台限制。
- 不经过本机代理的实际网络中，更新清单与 APK 下载是否可达。

最后一项尚不能从本机通过代理回下载成功得出结论。自站镜像仍待管理员配置，本报告不改默认下载源，也不把镜像配置当成缺业务 API。

### D2. 无障碍、窄屏和大字体需系统验收

当前已有图标说明、刷新可访问操作、搜索排序“向上/向下移动”等支持，不能说完全没做无障碍。既有 Lint 报告有 57 条 warning，其中 3 条涉及自定义触摸控件；部分控件已经手动调用 `performClick()`，警告需要逐项复核，不能直接算成 3 个用户故障。

仍需用 TalkBack、系统大字体、窄屏、横屏以及深浅主题验收主题缩略图、颜色选择、交互图谱、长表单和 PDF 工具栏的焦点、可读性与可点范围。优先修复实际阻碍操作的项，再处理绘制性能或可维护性建议。当前没有证据表明 57 条警告都是故障，也没有全量通过的验收记录。

依据：[ModuleOrderView][module-order]、[AppearanceActivity][appearance]、[OfficialThemeView][official-view]、[MobileStyle][mobile-style] 及 v0.2.22 既有 Lint 报告。

## 五、本次明确不列为“缺少”

| 类别 | 不重复列入的内容 |
| --- | --- |
| 已有业务 | 登录/记住账号/记住密码/自动登录、强制登录门禁、论坛与 Markdown 预览/图片、评论回复/点赞/收藏、云端多草稿/自动保存、投稿进度与修订重投、通知、全局搜索与历史、排行榜、题库/标签/收藏、本人和他人主页、OJ 绑定/核验/改绑/解绑/同步、账户注销与本机回执、Wiki 目录与章节导航 |
| 已有通用能力 | 页面返回栈/子页动画、下拉刷新、缓存后刷新及持续重连、主题库/本机主题导入分享/原图保留、背景裁剪、训练本地提醒、便捷管理、更新检查/下载/校验/系统安装、版本日志和人员署名 |
| 缺 API，按本轮要求排除 | 社团题单、按题讨论、私人错题本、间隔补题、目标打卡、完整公开成员目录搜索，以及未正式接入的翻译/AI 服务能力 |
| 之前已决定不做或后置 | 手机重管理、批量开户/CSV/复杂 Wiki 编辑、即时聊天/私信、手机判题、扫一扫、自主注册、完整离线业务数据与离线写入队列 |
| 正式版后续规划 | 目前按约定发布 0.2.x debug。正式渠道构建和长期签名交接需另行验收；不因“APK 能被解包”新增加固、混淆或更换证书任务。历史缺失 APK 也不在本轮补传 |

## 建议执行顺序

1. 先修 A1 发布首次失败和 A2 图片原页恢复，补对应回归。
2. 补 B1～B3 的帮助、数据说明、反馈与存储管理，同时处理 A3 当前状态文案。
3. 补 D1、D2 的设备回归与真机验收，再根据实际使用反馈决定 C1～C4 的阅读和分享增强。

本报告保留检查时结论；后续已选择实施的部分与暂缓部分分别在上方修改记录和后期计划追踪，不构成生产服务器已验收的结论。

[release-script]: ../Android_APP/tools/tag_release.py
[image-viewer]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/ImagePreviewActivity.java
[github-credits]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/GithubCredits.java
[handover]: android-maintainer-handover.md
[main-activity]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MainActivity.java
[about]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/AboutActivity.java
[response-cache]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/ResponseCache.java
[pdf-files]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/PdfFiles.java
[app-updates]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/AppUpdates.java
[manifest]: ../Android_APP/app/app/src/main/AndroidManifest.xml
[web-features]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/WebFeaturesActivity.java
[theme-share]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/ThemeShareProvider.java
[pdf-viewer]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/PdfActivity.java
[android-ci]: ../.github/workflows/android-ci.yml
[module-order]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/ModuleOrderView.java
[appearance]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/AppearanceActivity.java
[official-view]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/OfficialThemeView.java
[mobile-style]: ../Android_APP/app/app/src/main/java/com/giraffeslovebeauty/acmforever/MobileStyle.java
