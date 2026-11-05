# ACMforever 0.2.14：Tag 自动发布与 App 更新

> 执行补充：PR #96 已合并，签名 Secret 已配置，v0.2.14 首次 Action 因草稿按 Tag 查询返回 404 而失败，尚无公开 Release。用户已选择改发 0.2.15；当前修复与首发步骤见 [android-release-fix-v0.2.15.md](android-release-fix-v0.2.15.md)。以下保留 0.2.14 原方案和当时的准备状态，不能据其“未配置”描述判断当前配置。

状态：2026-11-05，实现及验收提交本次 PR 评审；未创建发布 Tag、未发布 Release、未操作生产服务器。仓库 `GiraffesLoveBeauty/ACM-Forever` 已按授权改为公开，原提交历史保留，匿名访问实测返回 200。

## 1. 范围与发布位置

采用现有公开仓库的 GitHub Releases 承载安装包。无需业务服务器新增安装包 API，不修改 `feat/api/`、`feat/web/` 或原服务器同步工作流。旧的自有服务器方案已被替代。

- 源码与工作流：本仓库，通过新 PR 评审、由另一位成员合入 `main`。
- 发布入口：[Android tag release](../.github/workflows/android-release.yml)，仅 `push` 版本 Tag `v*` 触发；无手动上传入口。
- APK、校验文件和清单：`https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/tag/vX.Y.Z`。
- App 固定更新来源：`https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/latest/download/update.json`。
- `versionCode` 在 APK 中写定，客户端比较远端清单的 code；`update.json` 是 Release 附件，不是提交到 Git 的动态文件。
- 当前 `0.2.14` / code `28` / 包名 `com.giraffeslovebeauty.acmforever` / minSdk26。

本轮只上传源码 PR；APK、签名私钥、缓存、测试截图和本机配置不进入 Git。不手工上传 Release，不在本轮创建 Tag 或合并。

## 2. 首次发布前的负责人配置

在仓库 Settings → Secrets and variables → Actions 配置。2026-11-05 实测尚无 Android 签名 Secrets；不声称首次发布条件已经齐备。

### 当前 0.2.x 调试分发

| 配置 | 类型 | 要求 |
| --- | --- | --- |
| `ANDROID_RELEASE_CHANNEL` | Repository variable | `debug`；未配置时工作流默认 debug |
| `ANDROID_DEBUG_KEYSTORE_BASE64` | Repository secret | **既有** `Android_APP/dist/signing/debug.keystore` 的 Base64；不能新建另一把密钥 |

由负责人在受控机器读取现有密钥并直接存入 Secret，勿贴在聊天、Issue、PR 或日志。现有 debug 使用 Android 标准别名/口令，长期保管密钥文件；它不会作为 Release 附件。

工作流固定核对既有证书 SHA-256：

```text
88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4
```

debug Release 标题及 APK 文件名都标注 debug，Release 本身使用普通正式发布状态（非 prerelease），使固定的 `/releases/latest/download/update.json` 可用。这是测试渠道分发，不代表已切换正式签名。

### 未来正式签名

设置 `ANDROID_RELEASE_CHANNEL=release`，配置四项 Secrets：`ANDROID_RELEASE_KEYSTORE_BASE64`、`ANDROID_RELEASE_KEY_ALIAS`、`ANDROID_RELEASE_KEYSTORE_PASSWORD`、`ANDROID_RELEASE_KEY_PASSWORD`，以及变量 `ANDROID_RELEASE_CERT_SHA256`（正式证书 SHA-256）。正式私钥长期保管，不能用调试密钥代替。工作流会检查实际 APK 为非 debuggable，并核对证书。

当前采用**单一 latest 更新流**。清单包含 `channel`，新客户端拒绝不同渠道，避免下载不兼容的包；一旦切正式渠道，旧 debug 用户需按既有约定先重装正式版。此流程没有承诺双渠道同时自动更新。未来若需并行渠道，须另行设计独立清单地址。

限制 Tag 创建权限、保护发布用 Secrets 由仓库负责人配置；本 PR 不声称已启用规则集或 Actions environment 审批。工作流本身要求 Tag 指向 `main` 上已有的提交。

## 3. 每次发布步骤

1. 在主题分支修改 App，递增 `app/app/build.gradle` 中的 versionName、versionCode，补齐 `assets/releases/history.json` 首条记录。code 必须大于最新已发布清单；正常流程也不得复用任何历史 code。
2. 运行适用测试、Lint、构建及更新合同测试，源码与文档分别提交。通过 PR 跨人 review，负责人确认发行内容。
3. 由非提交者合入 `main`；负责人确认签名配置和待发布提交。
4. 负责人从已批准的 `main` 创建 Tag 并推送。以下为 **0.2.14 首发时的操作示例，本轮未执行**，不能指向本机旧分支：

   ```sh
   git fetch origin main --tags
   git switch main
   git pull --ff-only origin main
   git tag v0.2.14
   git push origin v0.2.14
   ```

5. 在 Actions 查看 `Android tag release`；无需手工新建 Release 或附加本机 APK。
6. 工作流成功后核对 Release 的版本、源提交和说明，匿名访问清单与 APK，并在目标手机网络下验收下载及系统覆盖安装。

Tag 创建后不得移动或重写。发布失败可对同一 Tag 重跑失败工作流；若源码必须修正，通过 PR 并递增版本后发布新 Tag。仓库 Secrets、变量由运维设置，不通过源码 PR 携带。

## 4. Action 实际执行顺序

1. 检出触发 Tag 的完整历史，确认 HEAD 等于事件 SHA，且该提交属于 `origin/main`。
2. 检查 Tag 精确等于 `v` + versionName，code、当前离线日志和 Gradle 一致；拒绝 `v0.2.14-rc1` 等不支持的格式。
3. 执行 Python 发布合同测试；配置 Java17、Android35 和构建工具。
4. 从 Secret 解出临时签名文件；缺少配置立即失败，构建后始终清理临时密钥。
5. 执行对应渠道 JVM 单测、Lint 和 APK 构建；不会上传本机编译的旧 APK。
6. 通过 aapt/apksigner 核验实际包名、版本、最低系统版本、debuggable 属性、唯一签名证书及 APK 内的更新日志；计算真实大小和 SHA-256，复制后再次核对。
7. 检查仓库公开、versionCode 大于最新公开清单；同渠道固定证书不得改变。
8. 创建**草稿 Release**，附加 APK、`.sha256`、`update.json`；三件制品逐件下载回来比较哈希，再检查一次最新 code，全部成功后公开并标记 latest。

发布作业使用 `contents: write`；其余默认 `contents: read`。所有 Tag 发布共用串行并发组，不中断正在执行的发布。连续推多个 Tag 时 GitHub 可能替换尚未开始的 pending 作业，应逐个发布并等待结果。

公开之前失败会保留草稿和此前的 latest；重跑可覆盖草稿内附件。已公开的同 Tag 制品不可覆盖；只有本地清单、APK、校验文件与已公开附件完全相同才允许无修改地结束。脚本的 `publish` 子命令还要求匹配的 GitHub Actions Tag push 环境，防止误用本地发布命令。

GitHub Release 不提供跨所有维护者操作的数据库事务；不要在 Action 发布期间手工编辑附件、latest 或 Tag，也不要手工发布其他没有 `update.json` 的 Release，否则校验将停止并要求负责人处理。

## 5. 附件与清单

0.2.14 debug 的附件名：

```text
acmforever-0.2.14-debug.apk
acmforever-0.2.14-debug.apk.sha256
update.json
```

正式渠道 APK 为 `acmforever-X.Y.Z.apk`。清单由实际 APK 生成，含 packageName、versionName、versionCode、minSdk、channel、apkUrl、sha256、sizeBytes、signingCertificateSha256、notes；不手填示例哈希或伪造新版。notes 默认使用本版内置 summary/changes/notes，Release 正文同时记录源提交。清单不超过 32 KiB，notes 不超过 8000 个 Java UTF-16 字符。

APK URL 指向具体 Tag，已发布文件保持不变；latest 入口随成功发布切换。客户端不携带 GitHub Token、Cookie 或仓库密钥。下载通过 HTTPS，系统安装前仍核验大小、SHA-256、实际包名、递增版本、最低系统版本及与已安装包一致的签名。

## 6. App 交互

- 启动第 5 步：会话处理完成后、主页内容请求前异步检查；默认勾选自动检查，保留显式关闭，至少间隔 6 小时且每进程启动只调度一次。更新源故障不阻塞主页。
- 新版弹窗：中间显示版本号和可滚动更新说明，下方等大“下载安装包”与 50% 透明红色“取消更新”；旋转恢复、防重复打开。
- 用户点击下载后进入猫娘加载页，使用真实系统下载任务，显示进度、失败重试、取消和安装入口。返回后后台继续；没有 Wi-Fi 自动下载。
- 手动检查当前为最新：显示“已是最新版本”和“确认”。断网、HTTP404、渠道不匹配等只报真实错误，不冒充最新。
- 设置页保留本机更新清单覆盖地址；留空恢复 GitHub 默认地址。旧版已填写的自定义地址不擅自改写。
- 内置 28 版更新日志可离线查看；同签名覆盖安装保留账号选项、本机主题及图片，卸载/清除数据会删除。

旧 0.2.13 debug 默认使用尚未实现的业务端接口；首次迁移需手动安装本版或在旧包内设置本次固定清单 URL。已装旧本地 0.2.14/code28 的设备也不会自动提示另一个 code28；请手动同签名覆盖或等待下个更高 code。真实升级验收用 code27 → code28，不能只改 JSON 冒充升级。

## 7. Review 与发布验收

本次 PR 请重点 review：Tag/main/版本约束、固定签名和渠道切换、草稿三附件回读后再公开、失败重跑及已公开版本不覆盖、默认更新来源、启动顺序、弹窗生命周期、下载与安装校验。

本地合同/模拟器检查不能代替线上发布和真机覆盖安装。合并前看 PR 当前 head 的自动检查；首个 Tag 由负责人创建，随后验证匿名清单、APK 内容/签名、真实 code27 → code28 安装及本机数据保留。此 PR 路径不命中 `feat/**` 或服务器同步文件，合并本身不会触发既有服务器同步；发布只由 Tag push 触发。

出现问题不降级已装手机、不重写既有 Tag/附件；暂停下一次 Tag，按 PR 发布更高 code 的修复版。第一次发布前发生失败，latest 仍无清单，App 如实显示错误。

相关文件：[android-app.md（当前客户端说明）](android-app.md)、[安装说明-v0.2.14.md（本地验收）](../Android_APP/docs/安装说明-v0.2.14.md)、[tag_release.py（发布协调）](../Android_APP/tools/tag_release.py)、[create_update_manifest.py（实际制品验证）](../Android_APP/tools/create_update_manifest.py)。
