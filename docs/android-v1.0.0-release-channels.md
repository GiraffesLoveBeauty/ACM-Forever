# Android 1.0.0：正式版与待发布测试版

> 2026-11-16恢复实施。以下“本轮”以已发布0.2.30/code44、main `672427d9` 为基线；文末2026-11-08资料仅为历史，code37/38与旧制品哈希不能用于本次发布。状态：PR #150首轮本地Review两项P2已修复，当前修订待复审，未创建Tag或部署。

## 本轮版本与分发

| 项目 | 正式版 | 管理员待发布测试版 |
| --- | --- | --- |
| 名称 / 安装code | 1.0.0 / 45 | 目标1.0.0，preview.1 / 44（实际分发再读线上普通版code） |
| 包名/数据/证书 | `com.giraffeslovebeauty.acmforever`，保留数据、固定历史签名 | 相同包名和签名，覆盖；不会多一个App |
| 构建 | release，debuggable=false | preview，debuggable=false |
| 检查 | 默认开，每个手机本地04:00日最多一次主动尝试 | 所有自动检查关闭；手动正式渠道可返回普通版 |
| 下载 | Gitee优先、GitHub兜底，公开八附件 | 仅管理员手动；业务服务器鉴权代理私有草稿八附件 |

普通和测试APK互不内嵌。previewRevision独立递增，后续1.0.1测试版应沿用当时正式code45，正式1.0.1再提高到46。Android不支持从已发布正式code45无损降回旧code44；同code来回仅适用于相应普通版与其未来测试版本。共享数据格式须向后兼容。

公开清单使用schemaVersion2、distribution=release，省略旧channel字段，让未修改的0.2.30 debug客户端发现正式升级。正式包校验版本名/code、实际debuggable/渠道元数据、大小/hash与固定证书。只在首次正式发布前允许签名相同且code≤44的旧0.2.x debug包作为切回目标。

### 本地模块与系统安装回执

普通模块仍使用`optional-modules/<code>/`；测试模块使用`optional-modules/<code>/previews/<previewTag>/`。各目录分别保存`catalog.json`、`downloads/`和`installed/`，私有清单经管理员在线校验后原子保存，不能覆盖同code的普通清单。离线清单不含登录凭据，解析后下载地址为空、owner=-1；下载必须重新取得当前管理员绑定的spec。

资源复用继续校验原始归档签名和内容revision，解包回执同时保存源code与源previewTag；健康检查、修复按同一归属取清单和归档。仅已安装测试基础包对应的修订写入`.activated`，暂存未来修订不切换当前资源；普通版优先自身资源，没有配套资源时可保留此前真正启用且API兼容的资源。显式删除模块清理各版本和测试修订中的该ID，保留其他模块、主题、原图和账户数据。

普通更新的系统回执继续兼容`app-update`；测试回执带独立进程/会话控制器凭据，接收器送到`adminUpdates`。系统待确认、取消、失败都必须更新发起控制器；退出、换号、失去角色或进程重建后旧测试回执不恢复授权。系统确认仍由用户完成，不静默安装。对应真实窗口及变更资源回归见[本轮验收](android-v1.0.0-verification.md#pr-150-首轮-review-修复与新增回归)。

## 八附件与发布顺序

每种分发各自包含基础APK、`.sha256`、`update.json`、`modules.json`及四个模块（官方主题、高级个性化、便捷管理、分层素材），共八附件；两种分发不混装。

1. 完成本地实现、单测、实际APK/模块与迁移验收，再提PR交用户安排Review。当前待Review记录保持空；真实完成后补录PR、证据与人员，复核补录差异，才允许Tag。
2. 测试Tag `v1.0.0-preview.N`：Actions读取当前公开普通版code和签名，生成preview基础包及两原生split、两资源包。模块metadata与基础包同code，清单含previewTag与独立revision。
3. 测试八附件逐件回读后留在GitHub**未公开草稿**；禁止publish、更改latest或镜像Gitee。已存在测试修订不可覆盖，修复后增加N。
4. 正式Tag `v1.0.0`：仅构建正式八附件；回读验证完整性后公开，不带测试URL。Gitee当前为manual，维护者手动镜像同一套文件，不索要Gitee Token。
5. 正式发布后，同目标或更早测试修订自动从私有API的候选中移除。没有测试版本是200/available=false；源缺配置或故障是503。

固定证书SHA256：`88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4`，沿用既有`ANDROID_DEBUG_KEYSTORE_BASE64`（历史Secret名不影响debuggable）。不更换证书，不提交私钥。

## 管理员API与运维配置

| 请求 | 行为 |
| --- | --- |
| `GET /api/admin/android/releases/latest` | 实时会话/admin/root/首次改密校验；完整最新未正式发布候选与受限moduleCatalog |
| `GET /api/admin/android/releases/{previewTag}/apk` | 下载对应候选基础包，完整缓冲验hash后再校验角色 |
| `GET /api/admin/android/releases/{previewTag}/modules` | 对应候选的受限模块清单 |
| `GET /api/admin/android/releases/{previewTag}/assets/{name}` | 仅允许四个固定模块文件名，缓冲验hash后再次校验角色 |

匿名401、普通成员403、未首次改密428；返回private/no-store、Vary Cookie。角色在上游下载期间丢失时不得返回文件；换账号/退出后客户端取消传输与私有Provider授权。私有下载不走DownloadManager，进程恢复后需重新鉴权。APK≤150MiB、单模块≤16MiB，Token仅发往GitHub API，重定向CDN不带Token；客户端不接收Token、资产ID或临时签名URL。公共下载不携带业务Cookie。

服务器由运维安全配置`ACM_ANDROID_GITHUB_TOKEN`（仅需读取目标仓库未公开Release草稿的最小权限）及可选`ACM_ANDROID_GITHUB_REPOSITORY=GiraffesLoveBeauty/ACM-Forever`。不在聊天传私钥或Token，不将私有文件放到公开静态目录。无需更改数据库结构。

`feat/**`合并main会命中当前服务器同步流程。**合并前需完成运维确认及当前head的外部Review；未配置Token不能称线上测试下载已可用。** 未配置返回503，正常登录、论坛与公共正式更新仍可工作。回退时撤销本PR新增蓝图注册并移除专用Token；已安装测试包仍可手动切回当前不低于自身code的正式包。公开自站镜像继续等待，与本次私有鉴权代理分开。

本地验证和限制详见[android-v1.0.0-verification.md（本轮验收）](android-v1.0.0-verification.md)。真实草稿、线上凭据、真机/鸿蒙安装确认必须在Review后按授权发布再验收。

---

# 2026-11-08延期前设计与验收归档

> 本文为延期前的设计和本地验收归档。0.2.24 PR只保存此记录，不包含下述双渠道客户端、管理员分发接口、工作流或发布工具实现。对应源码、候选包、日志和备份均继续留在本地，未来单独提交并重新review。

> 2026-11-08延期记录：用户决定暂不发布1.0.0，继续0.x更新。本文保留当时的渠道设计、1.0.0/code38候选包摘要与验收结果，供下次发布复用；它们不是已公开版本。当前源码改为0.2.24/code38，见[本轮题目优化](android-v0.2.24-problem-reading.md)。下次1.0.0必须使用高于届时已发布版本的versionCode，不能照抄本文历史code38；测试版也须重新读取当时线上普通版的基线code。签名、同包名覆盖、独立下载与禁自动检查等实现和测试保留，重新发布前按新基线再验证。

状态：2026-11-08本地修订，尚未提交PR、上传、创建Tag或部署。基线main为d3a4e29fc541604cdf1b0f4ce9370815188a590b。本文已按用户澄清替换原先的独立管理员包方案；旧.admin包不再使用。

## 分发规则

| 项目 | 正式版 | 待发布测试版 |
| --- | --- | --- |
| 同一包名 | com.giraffeslovebeauty.acmforever | com.giraffeslovebeauty.acmforever |
| 签名、图标、数据 | 原固定签名与图标，沿用原数据 | 相同，覆盖正式版，不产生第二个App |
| 首版名称 / versionCode | 1.0.0 / 38 | 目标1.0.0，测试修订1 / 37 |
| Gradle变体 / debuggable | release / false | preview / false；测试分发不等于开放开发调试 |
| 可下载范围 | 普通公开发布渠道 | 管理员更新页手动选择，后端实时鉴权 |
| 自动检查 | 正式渠道，尊重已保存开关，默认开 | 所有自动检查关闭，忽略已保存的开启选项 |
| 手动入口 | 检查正式版；管理员额外有待发布测试版入口 | 检查正式版以切回；管理员另有待发布测试版入口 |
| APK内容 | 仅正式版，不内置测试APK | 仅测试版，不内置正式APK |

测试版不是独立的管理员工具，也不授予管理权限。普通账号看不到测试下载入口，强行启动内部页面仍由后端拒绝。测试版上的普通账号仍可手动切回正式版。

## 来回覆盖与内部版本号

Android通常拒绝安装更低的versionCode。为保留数据切回当前正式版，测试包沿用当前已发布普通包的versionCode；目标正式版使用更大的versionCode。previewRevision独立递增，不靠提高安装版本号区分测试修订。

本轮基线为已发布0.2.23/code37：可以覆盖安装1.0.0测试版/code37，也可以原路覆盖回0.2.23/code37。正式1.0.0发布时使用code38，此后测试1.0.1应沿用已发布正式版的code38，正式1.0.1再增加到code39。新正式版已发布后，不支持任意退回更低versionCode的历史版本。

公开正式清单使用schemaVersion=2、distribution=release，不输出旧channel字段，因此旧0.2.x客户端能够识别正式1.0.0。历史0.2.x公开debug包仅作为首次正式发布前的切回兼容，要求原签名、code不超过37及0.2.x版本名；不会重新公开发布开发debug包。

每个APK在AndroidManifest中保存acmforever.distribution、acmforever.preview_revision、acmforever.release_version_code。AppDistribution读取已安装渠道；安装前检查候选真实元数据、包名、版本、大小、摘要与固定签名。Android15归档flags可能为零，ApkManifest直接读取编译后清单的debuggable标志。两种新分发包均不可调试。

两种包共享本机数据，因此测试功能修改数据格式时必须保证当前正式版仍能读取；不能把签名一致当作业务数据向后兼容的证明。本轮没有引入新的主题、草稿或凭据存储格式。

## Tag与Actions流程

1. 本地修改、测试，交别人review，获确认后合并；当前阶段仅本地，不进行这些远端操作。
2. 待发布测试Tag使用v1.0.0-preview.1，后续修订递增preview序号。Actions从已发布普通清单取得实际versionCode，作为previewVersionCode传给Gradle，再校验同签名、未来正式版本及真实APK元数据。
3. 测试Tag只构建并保存一个测试APK及其sha256、update.json；stage-preview存入未公开草稿，逐件回读，永远不publish，也不更改公开latest。
4. 正式Tag使用v1.0.0，只构建并公开正式APK及其sha256、update.json；不生成或上传附带的测试APK。正式versionCode必须高于上一公开版。
5. 正式发布后，后端不再返回同目标版本或更早目标版本的测试草稿；没有待发布版本时返回有效空结果，客户端显示“暂无待发布测试版”。

创建过的Tag和制品不覆盖重写。正式与测试下载均只传输用户选择的那个APK；来回更换时另行下载目标包。构建清单工具拒绝APK内嵌另一个APK。

固定证书SHA-256为88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4。继续使用现有受控ANDROID_DEBUG_KEYSTORE_BASE64，不在仓库保存私钥。Secret的历史名称不决定APK是否可调试。Gradle本地默认preview基线仅用于构建验收；正式测试分发必须由发布脚本再次与线上普通清单核对。

## 受保护的测试下载接口

后端新增模块为feat/api/acm_api/android_release_api.py，复用Web会话和数据库实时admin/root鉴权；匿名401、普通成员403、首次改密未完成428。未配置或上游异常503；已配置但无待发布测试版时200且available=false。

| 请求 | 行为 |
| --- | --- |
| GET /api/admin/android/releases/latest | 当前未正式发布的最新完整测试清单 |
| GET /api/admin/android/releases/{previewTag}/apk | 所选测试修订的APK，下载完成并验哈希后再次核对权限 |

测试清单distribution=preview，packageName仍为普通包名；包含versionCode、releaseVersionCode、previewRevision、previewTag、apkPath、大小和摘要，不包含公开apkUrl。使用previewTag标识下载，不能用共享的versionCode区分测试修订。正式清单只列正式apkUrl，不含测试下载地址。

服务器需安全配置ACM_ANDROID_GITHUB_TOKEN，凭据账号具有读取目标仓库未公开草稿的权限；ACM_ANDROID_GITHUB_REPOSITORY默认GiraffesLoveBeauty/ACM-Forever。凭据只发往GitHub API，允许的制品跳转移除凭据，不向客户端泄漏Token、资产ID或签名下载URL。

私有下载不使用系统DownloadManager，不在整个传输期间占用ApiClient监视器；禁止同源Cookie重定向。进程退出、切账号、退出或权限失效使私有附件不可读，安装前重新核对管理角色。返回private/no-store和Vary Cookie，JSON最多32KiB、APK最多150MiB，临时文件不进入静态目录。正式下载继续保留系统下载恢复。

维护者不得手工公开测试草稿；仓库管理者本身能够读取草稿，拿到APK的管理员也可能自行复制文件，这不属于下载鉴权能阻止的范围。

## 上线边界与本地验收

本轮包含feat/api后端变更，将来合并main会命中既有服务器同步流程，需跨人review和运维确认；Vue网页没有修改。与等待中的公开自站镜像、Nginx、SSH配置无关。当前没有配置线上凭据、创建草稿、发Tag或上传任何安装包。

本地正式候选在Android_APP/dist/local-v1.0.0/release/，测试候选在同级preview/，各自包含一个APK、sha256和update.json，均忽略于Git。旧admin-debug候选已过时，不能用于本方案。

2026-11-08本地验收结果：

| 检查 | 结果 |
| --- | --- |
| Python发布契约 | 47项全部通过 |
| 官方主题资源 | 2项全部通过 |
| 后端测试版分发模块 | 9项全部通过；本轮未重跑后端完整测试集 |
| Java单元测试 | release、preview各188项，各187通过、1跳过、无失败 |
| Android Lint | 两种变体均0 errors、57项既有warnings |
| 构建 | 两种分发APK及仪器测试包构建成功 |
| Android 15/API 35模拟器 | 真实旧版→测试版→旧版→测试版→正式版覆盖通过，主往返过程中未卸载、未清数据，账号、Keystore加密密码、主题、搜索历史和私有文件保留 |
| 旧版升级发现 | 真实0.2.23/code37客户端能够读取本轮正式code38清单并识别更新 |
| 测试版检查行为 | 不发自动更新请求，保留手动普通渠道入口和旧包验签切回 |
| 管理员下载 | 独立隔离场景验证preview.1下载真实preview.2、修订/目标版本/签名/哈希校验、只读Provider、退出后失效及有效空结果 |
| 原有回归 | startupupdates、creditslogin、lifecycle、recoverysettings通过 |

最终本地制品：

| 制品 | 字节数 | SHA-256 |
| --- | --- | --- |
| release/acmforever-1.0.0.apk | 3,052,316 | 699abfa02bcc82b46eee413a90c18e863fad209c246ed9ac7df50fe8abb7fe04 |
| preview/acmforever-1.0.0-preview.1.apk | 3,052,312 | 48fa1706afed0b52b31ebae8e50dfc41677061a962afbb6adf61d4ac3fd46816 |

两份包各自约2.91MiB，均经真实SDK工具核验，不互相内嵌。构建与验收日志分别为Android_APP/dist/build-v100-preview-final.log、smoke-v100-preview-final.log、release-preview-tests.log、theme-preview-tests.log和api-preview-tests.log。Git diff空白检查通过，APK与日志均被Git忽略。

上述为本地和模拟器结果，不代表所有真机或鸿蒙已通过。真实GitHub草稿、服务器凭据与线上权限仍须在后续review及部署后另验；当前没有提交、上传、创建Tag、发布或部署。
