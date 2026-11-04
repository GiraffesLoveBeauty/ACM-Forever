# ACMforever Android v0.2.13

状态：PR #48 待评审版本，2026-11-04。包名 `com.giraffeslovebeauty.acmforever`，版本 `0.2.13` / code `27`，minSdk 26、target/compile SDK 35。当前交付为本机调试签名 APK。

## 范围与目录

`Android_APP/app/` 为 Java 原生 Android 工程，`app/app/src/androidTest/` 是独立测试包，`Android_APP/prototype/` 是历史浏览器原型，不代表当前 Android 版本。`Android_APP/docs/` 保留每版安装、美术与需求记录；本文与根 `docs/api.md` 说明当前工程行为。`dist/`、SDK/JDK/Gradle、依赖、数据库、签名密钥及构建缓存不入 Git。

底部入口为论坛主页、排行榜、发帖、题库和个人中心，顶部头像进入账号设置。现有接口复用于登录、论坛、收藏、多草稿及自动保存、投稿进度、Markdown 预览/图片、题库与 PDF、通知、Wiki、训练与赛事复盘。手机不直接连接数据库，不携带服务端 Bot Token。重管理与 OJ 绑定操作留在 Web，App 提示转网页或联系管理员。

个人中心包含公开资料、各平台通过题数和本人最近 AC；公开逐题记录不向他人开放。外观支持独立主辅色、模块/控件透明度、相册裁剪全屏背景、网页主题的原生适配及本机主题保存/编辑/预览/删除。背景、主题、历史与凭据仅保存在设备，凭据使用 Keystore AES-GCM。相同包名与证书覆盖安装保留这些数据；卸载或清除应用数据会删除。

运行资源包括用户提供的分层角色图、既有剪影和平台标志，来源记录位于 `Android_APP/docs/artwork-v2/` 与各版美工文档。搜索旁加号沿用用户指定的参考资源，完整参考素材库未打包；代码仓库不代替第三方资源授权。原 0.1.x 管理/浏览器/更新壳作为历史代码保留，当前 Gradle 排除其类及 `assets/admin/`。

## 后端整合与迁移

PR 复用主线 Web 会话、CSRF 和业务 API，仅为公开成员身份/资料/帖子补 `/api/mobile/v1/*`，并为公开排行榜增加可选 `period=today`、`positive_only=1`。详见 [api.md（移动端契约与排行榜）](api.md)。浏览器评论用例改为按创建接口返回 ID 等待对应节点，避免桌面/手机视口共享临时库时误选旧评论；注销重开户测试在请求 API 切换账号前停止管理员页面刷新，避免旧响应覆盖新 Cookie；不改网页产品代码。本次在旧 PR 最新 head 上整合 main `afb5f0d119cf1dc5bdab3869e05568389b223a8f`，保留通知、Markdown、Wiki、论坛修订与账号生命周期功能。

草稿 P1 修复后继续整合 main `a9b8966a0edf7f0736f1647194baa51c240b989c`，恢复因文档冲突受阻的 PR 检查。手工只合并 API README 的移动资料说明与最新部署路径；主线账号 Excel 导入开关、QQ 导入凭据及公网部署实现原样保留，未修改其业务设计。账号相关 121 项、移动接口 7 项、Web 构建和 248 项测试补测通过。Android 源码和实际 APK 不变；只更新 PR 分支，不合并 main 或操作生产。

移动公开身份表增加 `account_epoch`；迁移旧表时默认第一代，再为同 QQ 新代账号生成新 ID 并清空旧座右铭。注销者的公开主页/帖子列表返回 404，保留的旧论坛内容匿名，不关联重新创建的账号。写资料时在事务中再次验证当前 actor。App 已去掉座右铭入口，旧接口仍兼容。

排行榜先读取移动能力：支持 `public_member_ids` 时使用 `/api/mobile/v1/leaderboard`，否则使用 `/api/community/leaderboard`。零 AC 兼容分页在同一次查询中保持接口一致，避免丢失公开成员 ID。榜单成员可通过现有移动资料/帖子接口打开公开主页；旧服务器没有公开身份时不伪造 ID。review 5765456345 指出旧请求绕过了这一步，本轮已修复并补充回归。

论坛列表和详情也通过 `api.publicPostsPath(suffix)` 选择移动接口，保留分类、搜索、分页及详情的 `comment_id` 查询参数。只有移动读取接口补充 `author_public_member_id`；发帖、评论、点赞等写操作继续复用现有 Web API。旧服务器能力接口返回 404/405 或明确不支持时，仍用普通接口读取正文，不伪造公开身份。

云端草稿由 Application 在进程内持有。编辑 A 后从草稿列表选择 B，返回旧编辑页时完整同步当前 B 的标题、正文、分类、ID 和草稿代次，并重建输入控件；A 在进入列表前先保存。旧控件的写入和旧页面的 flush 必须匹配绑定代次，迟到的读取、保存、提交、删除及 Markdown 导入不能改写新选草稿。评论 6628388380 的 P1 已用旧构建复现，并补充真实三 Activity 返回与写入记录回归。

选择 Markdown 的账号与草稿代次单独写入 Activity 实例状态，并仅在会话一致时恢复，不放入页面返回栈。正常 Activity 重建可继续导入，真正的账号或草稿切换仍拒绝迟到文件结果。Wiki 的 `/problem.html?platform=…&problem_id=…` 相对关联练习直接进入原生题面与样例，返回原文章；只匹配无 scheme、无 authority 的确切路径，缺少查询参数时提示错误，其他外链继续要求 HTTPS。

服务地址由 Application 在进程启动时配置一次，非法保存值也在此清理；MainActivity 创建和重建仅复用共享客户端，不重复调用持请求锁的 `setBaseUrl()`。慢请求或云端自动保存期间重建页面无需等待网络返回，账号和草稿的串行保护继续保留。

缺少接口、无网络、服务器错误、未登录和暂无内容独立处理。已成功请求的页面先显示缓存再后台刷新；持续失败可关闭红色提示，重连成功绿色提示 3 秒关闭。没有缓存时显示真实错误，不伪造业务数据。测试通过不代表生产接口已经部署。

## 更新渠道与说明

- `assets/releases/history.json` 保存 27 版更新日志，检查更新页离线可读，构建时检查当前版本一致。早期没有详细记录的版本明确标作存档。
- 调试包默认使用当前 API 根地址的 `/api/mobile/v1/releases/latest?channel=debug`，此自有服务器发布接口尚待实现。
- 正式包默认使用资源 `default_update_manifest_url` 的 GitHub Release `releases/latest/download/update.json`；用户可以覆盖为独立 HTTPS 清单地址，留空恢复当前渠道默认地址。
- 清单至多跟随五次 HTTPS 跳转，每次拒绝 HTTP 降级、URL 凭据和 fragment，大小上限 32 KiB；不附业务登录 Cookie。
- 客户端校验包名、版本、minSdk、大小和 SHA-256；下载后再次核对实际 APK 包信息与当前签名。签名不符、旧包、错误哈希不会进入安装步骤。最长 APK 150 MiB。
- 自动检查与仅 Wi-Fi 自动下载均为可选，自动检查间隔至少 6 小时。系统下载继续执行，安装始终由用户在 Android 安装器确认。

## 当前调试安装包怎样分发

本次 PR 只上传源码，不把 APK 提交进 Git。当前安装包在独立整合工作区的 `Android_APP/dist/acmforever-0.2.13-debug.apk`，可先直接发送给成员手动覆盖安装。

若要让已安装的调试包在 App 内更新，需要单独上传同调试签名的新 APK 到 HTTPS 文件服务，并同步发布其真实 JSON 清单；在“检查更新 → 设置发布地址”填入这个固定清单地址。每次先上传/核验版本 APK，最后更新清单，保持旧安装包地址仍可访问。APK 文件可由自有服务器或单独的 GitHub Release asset 托管，但 GitHub PR 的源码地址不能当下载清单使用。当前默认的 debug 自有服务器 API 尚未实施，因此只推 PR 不会使手机收到新版本。

客户端只提示 `versionCode` 严格更大的版本。本次整合继续沿用 `0.2.13` / code `27`，若手机已装同 code 的旧本地包，应手动覆盖；后续发布必须递增 code 并补日志。正式签名与当前调试签名不同，不能覆盖安装，首次切换正式版需重装；此后保持正式密钥即可连续更新。

## 构建与 CI

使用 JDK 17、Gradle 8.9、AGP 8.7.3、SDK/build-tools 35。标准命令：

```sh
cd Android_APP/app
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug
```

Windows 现有离线工具链可运行 `Android_APP/tools/build-local-v0213.ps1`、`verify-local-v0213.ps1` 和 `package-local-v0213.ps1`，分别构建、运行十二组模拟器检查及核验实际包。脚本使用 `%TEMP%/acmforever-build-v0.2.0` 下已安装的工具和模拟器，不能视为从零安装脚本。调试密钥放 `Android_APP/dist/signing/debug.keystore`；缺少原密钥的机器会生成不同调试签名，不能覆盖已有包。

`android-ci.yml` 在 App/相关工作流的 PR 变更时执行发布清单 Python 测试和 Android JVM/Lint/构建。`api-tests.yml` 执行 Vue 构建、后端合同和 Web 单测。模拟器十二组测试目前是本机验收，不谎称已加入 Actions。

## 正式发布操作（本轮不执行）

远端已有 `android-release.yml`，本次保留并修正工具链/清单生成。发布前必须由维护者配置 `ANDROID_RELEASE_KEYSTORE_BASE64`、`ANDROID_RELEASE_KEY_ALIAS`、`ANDROID_RELEASE_KEYSTORE_PASSWORD` 和 `ANDROID_RELEASE_KEY_PASSWORD`，长期保管正式签名，不使用本机调试密钥代替。

正式发布顺序：完成跨人 review 与上线验收 → 按仓库规则合并 → 为批准源码建立与 APK 一致的 `vX.Y.Z` tag → 发布非 prerelease 的 GitHub Release。工作流检出该 tag，运行单测/Lint、构建正式签名包，核验签名和 aapt 实际包信息，比较 APK 内置日志与源码，再生成 `acmforever-X.Y.Z.apk`、`.sha256` 和 `update.json`，先附加 APK/校验文件，再附加 update.json 到该 Release。Release 正文作为远端更新说明，空正文使用本版内置日志。

发布工具拒绝 tag、包名、版本、minSdk、内置日志不一致及超限说明，计算真实文件大小/哈希并在复制后再次验证。失败时停止，不能发布伪清单。清单被客户端读取成功，才表示远端更新来源可用。GitHub 下载在目标手机网络下能否访问仍需发布后的真实设备验证。

只推 PR 分支不会部署；PR 含 `feat/api/**`，合并 main 将触发服务器同步，必须先由运维备份数据库、WAL、环境配置并确认迁移和恢复方案。本轮不合并、不发布 Release、不操作生产服务器。

## 历史评审逐项核对

2026-11-04 按当前代码和回归核对；“新 review 没再提”不作为修复依据。

| 评审问题 | 当前实现与证据 |
| --- | --- |
| 旧 `MainActivity` URL 编码 API 33 重载 | 已替换为 `UrlEncoding.form()`，调用 API 26 可用的 `URLEncoder.encode(value, "UTF-8")`；编码回归覆盖中文及特殊字符，Lint 检查最低 API 兼容性 |
| 未启用自动登录时 Activity 重建丢会话 | `MainActivity` 从 `AcmApplication` 取得同一 `ApiClient`；新增模拟器实际 `recreate()` 回归，核对关闭自动登录时 Cookie/CSRF 会话对象和代次保留。该保证不包含关闭自动登录后的进程重启 |
| 远端注销失败跳过本地清理 | `ApiClient.logout()` 的 `finally` 清会话并调用清理回调；断网、500、正常及重复退出的单测覆盖本地密码、持久会话和自动登录选项；模拟器另测断网退出 |
| 旧 `UpdateManager.java:303` 生命周期问题 | 旧类仍保留，未把旧实现本身标作修复；Gradle 已将其排除，当前 APK 使用 Application 持有的 `AppUpdates`，Activity 弱引用、解绑和存活检查负责界面回调；更新页面回归覆盖当前流程 |
| `ApiClient` 排行榜绕过移动接口 | 已按能力选接口，兼容分页保持同一接口；单测和模拟器验证公开身份、资料、帖子及返回榜单 |
| review 5766008716 的论坛列表/详情 P2 | 两处读取改为 `publicPostsPath`；单测覆盖移动及旧服务器，模拟器分别从列表和详情点击作者、获取资料和帖子后返回，并验证通知 `comment_id` 保留 |
| [评论 6628388380](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/48#issuecomment-6628388380) 的恢复编辑页草稿串写 P1 | 源码修复为 44b90e7，c4407b1 是文档；恢复时完整同步草稿及控件，CloudDrafts 拒绝旧代次写入/flush。4 项单测及三 Activity 回归先失败后通过，本轮再次通过，旧 A 输入回调不能写入 B |
| [review 5767651654 的 Wiki P2](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/48#discussion_r4467001493) | 先识别站内题面路由再校验外链；实际验证 Wiki → 原生题面/样例 → 原文章，HTTPS 外链保持外部 Intent，不完整参数报错；旧代码失败、修复后通过 |
| [review 5767651654 的 Markdown P2](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/48#discussion_r4467001498) | 同会话恢复导入归属；实际 recreate 后使用模拟文件选择器结果导入/自动保存，切换账号和草稿仍拒绝且不写入；旧代码失败、修复后通过 |
| [review 5768177626 的网络锁 P2](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/48#discussion_r4467398917) | 删除 MainActivity 重复 setBaseUrl，启动配置/非法偏好清理由 Application 统一完成；旧代码在 GET 挂起时重建失败，修复后 GET 和自动保存挂起期间均完成真实 Activity 重建及主线程心跳，保留会话/草稿和保存结果；另增 2 项配置单测 |

## 验证记录

debug 与 release 构建分支均完成单测/Lint/打包及实际清单生成检查；release 分支仅借本机调试密钥验证签名配置，没有正式签名制品发布。最终本机结果见 [安装说明-v0.2.13.md（实际 APK 与回归结果）](../Android_APP/docs/安装说明-v0.2.13.md)。生产更新源、正式私钥构建、远端 APK 下载与真机安装仍需发布验收，本机模拟响应不作为这些流程已通过的证据。

网络锁修复前的 `b041a471db892c9f704e2be6048bdaaf8fe1a6ca`，API、Android、browser 三项 CI 均已成功，属于旧 head 结果。本轮修复后，debug/release 各 67 项单测、十二组界面回归、9 项发布清单测试及实际 APK 清单核验通过；上轮 Wiki/Markdown、旧 P1、论坛作者主页与 Activity 重建会话再次通过。新增回归先在旧代码失败，后在修复后通过；证据路径见安装说明。新提交的远端检查按其 head 另行核对，本轮未修改后端或网页。
