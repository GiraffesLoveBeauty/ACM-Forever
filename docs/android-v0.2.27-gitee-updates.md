# Android v0.2.27：Gitee 优先更新与完整镜像发布

日期：2026-11-15。当前为 **0.2.27 / versionCode 41 / debug**，PR #141 已完成第二轮本地 review 并合并为 `931ffa7718a867bee9d1cf7c0a61993ae545517a`；上一公开版本为 v0.2.26/code40。用户确认 Gitee 由其手动同步，因此发布工作流小修另提 PR，尚未创建 Tag 或发布 v0.2.27。**App 的 Gitee 优先级保持不变，发布端是否自动同步是独立设置。** 1.0.0 和自站更新仍独立等待。

## 可行性实测

用户指定的 [Gitee 仓库](https://gitee.com/MJJ13445/ACM-Forever) 是公开仓库，默认分支 main。匿名访问仓库 API 和原始 README 成功，已导入 v0.2.14～v0.2.26 Tag；但 Release 列表为空，根目录没有 update.json。导入 GitHub 源码与 Tag 不会导入 Release 附件。

另以公开项目 dromara/Jpom 的40字节 `.sha1` 附件实测：浏览器下载 URL 与官方附件下载 API 均可匿名 HTTPS 下载，重定向到 `foruda.gitee.com`，内容一致。这证明服务能力可用，**不代表本项目尚未发布的 APK 已经在 Gitee 可用**。本项目首次发布必须完成下方凭据配置和全部附件回读。

参考接口定义为 Gitee 官方 [OpenAPI Swagger](https://gitee.com/api/v5/swagger_doc)：Release latest、按 Tag 查询、创建及修改 Release、`attach_files` 上传与列表。未使用网页登录 Cookie 或模拟上传私有接口。

## 客户端行为

1. 默认入口为 `https://gitee.com/api/v5/repos/MJJ13445/ACM-Forever/releases/latest`，读取正式 Release 的 Tag，再读取该 Tag 下的 `update.json`。
2. 清单校验包名、版本、渠道、大小、SHA-256；Gitee 入口额外要求 Tag、APK URL 与 modulesUrl 都属于同仓库同版本。预发布、404、超时、HTML 登录页、错误 JSON 或不合法清单均尝试 GitHub 原更新清单。
3. Gitee 已有更新且比本机新时优先使用它。Gitee 版本不高于本机时，另尝试 GitHub，防止镜像延迟隐藏已发布更新；GitHub 失败仍保留有效的 Gitee 结果，同版本优先 Gitee。
4. Gitee APK 由系统 DownloadManager 下载。系统报告传输失败时最多切换一次同版本同渠道 GitHub URL；空间不足、设备存储不可用及文件已存在不切源。手动取消不重试；APK 哈希/包名/版本/签名失败不会绕过验证。系统自行暂停和重试期间不同时开启另一份下载。
5. 模块清单按同版本 Gitee → GitHub → 本机有效缓存；Gitee 模块下载失败后尝试同版本同模块 GitHub 文件。每次仍校验大小、哈希，安装前校验实际签名与版本。已下载模块与设置保留，不下载用户未选择的模块。
6. 更新页显示首选地址、兜底说明和最近成功来源。用户手工设置的清单地址只访问该地址，不擅自重置；保存空地址恢复 Gitee 优先默认值。旧版自动检测开关、先会话后检查、更新弹窗、手动下载及系统确认安装的流程保持。

旧版用户尚无此默认源，需要先通过 GitHub 或从 Gitee Release 手动下载一次新版；安装后使用新默认值。相同包名和固定证书覆盖安装保留数据。自行设置过地址的用户须清空自定义地址才使用默认优先级。

## Tag 自动发布与配置

仍由 GitHub Actions 编译一次基础包与原生模块，沿用固定 debug 签名；Gitee 不重新编译，不上传 APK 到源码 Git。

```mermaid
flowchart TD
    A[源码 PR] --> B[其他成员 Review 与 CI]
    B --> C[确认后合并并创建新版本 Tag]
    C --> D[检查版本与固定证书 / 自动镜像模式才检查 Gitee Secret]
    D --> R{同 Tag 的 GitHub Release 已公开?}
    R -->|否| N[编译测试签名]
    N --> E[GitHub 草稿上传八附件并回读]
    E --> F[公开 GitHub Release]
    F --> M{Gitee 同步模式}
    M -->|manual 默认| X[用户手动同步同版 Tag 与全部附件]
    M -->|automatic 可选| G[同步同一个源码 Tag 至 Gitee]
    R -->|是| V[核对源码提交 / 版本 / 渠道 / 固定证书]
    V --> W[下载并校验八个原始附件 / 跳过重新构建和 GitHub 发布]
    W --> M
    G --> H[Gitee 创建预发布 Release]
    H --> I[上传同字节 APK 和模块 / 改写两份 JSON 地址]
    I --> J[匿名回下载全部八附件并核验]
    J --> K[切换 Gitee Release 为正式发布]
```

发布模式由 GitHub Actions Repository Variable `GITEE_MIRROR_MODE` 控制，缺省为 **`manual`**，另一个允许值为 `automatic`；其他值会被拒绝。在默认手动模式下，工作流完整编译、签名、验证并公开 GitHub 八附件，跳过 Gitee 凭据检查和远端写入，不需要配置 Gitee Token。客户端仍按 Gitee → GitHub 检查更新；Gitee 尚无同版 Release 时使用已有兜底逻辑。

仅在将模式设为 `automatic` 时，管理员还需在 GitHub 仓库 **Settings → Secrets and variables → Actions → New repository secret** 配置 `GITEE_RELEASE_TOKEN`，使用对 `MJJ13445/ACM-Forever` 有仓库写入与 Release 附件操作权限的 Gitee 访问令牌。只在 Secret 保存，不写入源码、App、聊天、URL 或日志。当前只读检查确认该 Secret 尚未配置；按用户选择使用手动模式，不创建或索取令牌。

自动模式在编译及公开 GitHub Release **之前**检查 Secret 非空。Gitee 写凭据仅供发布 Action 使用；App 全程匿名下载。自动同步只推送本次 Tag 及其源码对象，不改 Gitee main、GitHub main、网站部署和业务数据库。已有同名 Gitee Tag 指向别处时拒绝移动。

八附件：基础 APK、对应 `.sha256`、`update.json`、`modules.json`、`module-advanced.apk`、`module-admin.apk`、`module-official-themes.acmpack`、`module-cat-art.acmpack`。Gitee 两份 JSON 的 URL 改为 Gitee 同版本地址，APK与四模块字节、体积、哈希及签名不变；不要求两站 JSON 字节相同。

手动同步需要在 Gitee 创建同版 Tag 和 Release，并上传上述八附件；源码镜像导入不等于附件同步。APK、四模块和 `.sha256` 使用 GitHub 首发原文件；`update.json` 的 `apkUrl/modulesUrl`、`modules.json` 的四个下载 URL 改为 Gitee 同版路径，保留全部版本、大小、哈希及签名身份字段。`gitee_release.mirror_files()` 可从下载的 GitHub 八附件在本地生成两份 Gitee JSON，不执行远端写操作。不要重新打包模块或修改哈希来凑匹配。

可选自动模式下，Gitee 没有本流程使用的 draft 字段，以 `prerelease=true` 暂存；最新版本检查拒绝预发布。所有附件匿名回读正确后才切 `prerelease=false`。PATCH 同时携带官方 API 要求的 `tag_name`、`name`、`body`，保持已确认的版本、标题和说明不变。已公开附件不可替换，完全一致的重跑只校验；中途失败的预发布可在同 Tag 重跑时补齐缺失文件，已有文件不同则阻止。不能删除 Tag、覆盖 APK 或略过回读来解决失败。

GitHub 先发布、Gitee 后同步，跨站不是原子事务。手动同步由用户负责；可选自动模式的后半段失败时，GitHub 可能已公开、Gitee 仍预发布，修复配置/网络后重跑原 Tag 工作流。App 可兜底 GitHub；Gitee 旧正式版低于本机时，客户端会检查 GitHub 较新版本。国内网络、Gitee 配额、令牌权限及下载策略仍需首次真实镜像验收。

重跑时，`gitee_release.py --restore-github` 在构建前检查同 Tag 的 GitHub Release。未发布或只有草稿时执行原构建/草稿事务；已正式公开时必须确认公开仓库、真实 Tag 解引用后的 commit、Release 源码标记、源码版本/code、当前渠道及固定证书，再下载并校验原始八附件的完整性、URL、体积、哈希与校验文件。验证成功才输出 `reused=true`；随后跳过 SDK/密钥配置、编译、打包及 GitHub 发布，直接镜像原始字节。恢复失败即终止，不退回重新构建；输出目录非空时拒绝混入其他制品。资源包 ZIP 时间戳和签名可能随重新打包变化，因此即使源码和密钥相同也不能用新包替换首发附件。

## 验证与 Review

本轮本地验证结果：

- 首轮 Android JVM 测试 **214 项通过，0 失败**；主题资源测试 **2 项通过**。本轮 review 修复只涉及发布脚本、工作流与文档，APK 源码和本地测试包不变。
- 修复后发布、署名与 Gitee 镜像/恢复契约测试 **68 项通过，0 失败、0 跳过**；actionlint **v1.7.7** 检查发布工作流通过。
- Lint **0 errors / 68 warnings**；基础 debug APK、advanced/admin 原生模块和 instrumentation APK 均构建成功。
- 模拟器 `giteeupdates` 通过：默认 Gitee、新版本优先且不请求 GitHub 清单、源故障兜底、实际更新页来源文案、Gitee CDN 重定向、模块同版本切源、取消与临时文件清理、自定义源保持。
- 模拟器 `startupupdates` 通过：默认勾选及关闭记忆、会话恢复后检查、进程内去重、弹窗版本与说明、同尺寸按钮及取消色、重建、下载/重试/取消、最新版本确认、失败重试及六小时节流。

新增测试涵盖源顺序、异常/非法清单兜底、自定义源、镜像延迟、同版本 APK URL、模块 URL 白名单、发布完整性、失败恢复和不可变附件。模拟器使用合成 HTTPS 传输，不访问生产账号或向 Gitee 写入测试附件。真实网络只进行了前述匿名读取；凭据未配置，**尚未验收本项目 Gitee 的真实 Tag 推送、Release 写入、附件大小配额及完整 APK 下载**。上述发布测试使用内存夹具，不能代替首次真实发布验收。本机日志保存在被忽略的 `Android_APP/dist/gitee-v0.2.27-local/` 及同级构建日志，不提交源码库。

Review 重点：跨源仍只安装相同身份的制品；取消与重建不启动无限重试；Gitee Tag 不覆盖；令牌不进客户端与日志；自动镜像八附件全通过才公开；GitHub 既有发布校验仍有效。手动模式无需 Gitee Secret；如启用自动镜像，发布前需配置 Secret 并确认 Gitee 空间/权限。

## PR #141 首轮 Review 修复

本地报告 `PR141-v0.2.27-Review结果.md` 审查提交 `c4e114e1702dcc591cfef5dc8f33c5ca2eb9c965`，提出一项 P1、一项 P2。本轮补全 Gitee PATCH 必填字段，并为工作流增加已公开原始制品恢复分支。测试夹具现强制检查 PATCH 三字段及其值；恢复回归使用同一资源与临时 RSA 密钥实际打包、签名两次，确认两包不同，随后从模拟 GitHub 首发附件恢复，完成中断的模拟 Gitee 发布，且不覆盖已公开附件。还覆盖错误 Tag/commit、渠道/证书/版本、缺失/重复/损坏附件、非空输出目录和 Actions 输出门禁。

本轮没有调用真实 Gitee 写接口，没有合并、创建 Tag 或发布。修复提交需重新交其他成员 review。修复日志在被忽略的 `Android_APP/dist/release-v0227-review-fix-tests.log`；首轮 APK 与模拟器验收证据继续保留。
