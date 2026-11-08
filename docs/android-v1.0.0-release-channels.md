# Android 1.0.0：正式版与待发布测试版

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
