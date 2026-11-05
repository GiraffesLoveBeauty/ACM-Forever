# 自站优先的 Tag 发布与更新（从原 PR #100 拆分）

> 本PR独立基于main，保留原#100的自站客户端、发布脚本、Nginx示例和说明。2026-11-06 按授权配置新机 SSH 上传、旧机 Funnel 下载入口；具体状态与运维方式见 [Funnel 下载运维](android-funnel-mirror-operations.md)。原#100中的App功能另入独立PR，本分支不改应用Name/Code及日志。下面v0.2.16/code30/Tag/地址均为原方案示例，正式发布必须使用届时main的实际版本与更高versionCode，不能把示例当作已发布版本。

状态：2026-11-06 下载通路已通过GitHub-hosted runner的SSH上传与公网完整回读验收，仍待跨人评审及手机验证；未创建 Tag 或发布 APK。debug 渠道沿用原证书。

## 当前问题与地址

0.2.15 的清单、APK 都在 GitHub Release，国内网络可能无法直连。0.2.16 保留 GitHub 作为发布源与备用下载，同时让清单和 APK 优先走网站 HTTPS 静态目录。

- 自站清单：`https://cjluacmpanel.tail1b9e55.ts.net/GiraffesLoveBeauty/ACM-Forever/releases/latest/update.json`
- GitHub 备用清单：`https://github.com/GiraffesLoveBeauty/ACM-Forever/releases/latest/download/update.json`
- 示例自站 APK：`https://cjluacmpanel.tail1b9e55.ts.net/GiraffesLoveBeauty/ACM-Forever/releases/download/v0.2.16/acmforever-0.2.16-debug.apk`
- 对应 GitHub APK：上一路径的域名换为 `github.com`。

拟用自站清单在首次镜像发布前返回 404，**以上示例 APK 地址尚未发布，不是现在可下载的链接**。App 默认 URL 在 `strings.xml`；工作流的 `DOWNLOAD_ORIGIN` 必须与它一致。SSH 上传仍连接新机；HTTPS 回读连接旧机的 Funnel 公网入口，两者不要求使用同一域名。

## 运维首次配置

1. 选择持久化目录，推荐 `/srv/acmforever-releases`。不要使用部署时整体替换的 `acm-forever-feat`。如用 `acm-forever-data/releases`，先验证 Nginx worker 遍历权限；不能为了静态文件全局放宽 `/root` 权限。
2. 创建专用非 root 上传账号，只给此目录写权限和 Nginx 必要读取权限；服务器需要 Python **3.9+** 和 tarfile 标准库。上传目录内文件由脚本设为 0644、版本目录 0755。
3. 直连 HTTPS 方案可在现有 HTTPS `server {}` 加入 [Nginx 模板](../Android_APP/deploy/nginx-releases.conf.example)。当前采用 [Funnel 下载运维](android-funnel-mirror-operations.md) 中的 loopback 静态源与 SSH 隧道；URL 前缀用 `alias` 指向同一目录，禁止目录列表、隐藏文件和写方法。校验 `nginx -t` 后 reload；以后上传静态文件不用重启业务。
4. CDN 对该前缀的错误和 `latest/update.json` 禁用缓存；首次上线清除旧 404。模板使用 `no-store`，避免切换版本后仍读旧清单。
5. 给专用账号配置 SSH 公钥；在可信管理渠道核对服务器 host key，不在 Action 临时 `ssh-keyscan` 后直接信任。用外网可达地址，GitHub runner 不能直接访问 Tailscale 内网地址。
6. 配置以下 Actions Variables 与 Secrets。不要复用网站部署私钥或将密码、密钥写入源码；本次运维已设置仓库级镜像配置。

| 类型 | 名称 | 用途 |
| --- | --- | --- |
| Variable | `ANDROID_MIRROR_HOST` | runner 可达的服务器域名/IP |
| Variable | `ANDROID_MIRROR_PORT` | SSH 端口，空则 22 |
| Variable | `ANDROID_MIRROR_USER` | 专用非 root 上传账号 |
| Variable | `ANDROID_MIRROR_ROOT` | 例如 `/srv/acmforever-releases`；必须与 Nginx alias 完全一致 |
| Secret | `ANDROID_MIRROR_SSH_KEY` | 专用 OpenSSH 私钥全文 |
| Secret | `ANDROID_MIRROR_KNOWN_HOSTS` | 可信渠道核对的 known_hosts 行；非 22 端口使用 `[host]:port` |
| 原有 Secret | `ANDROID_DEBUG_KEYSTORE_BASE64` | 沿用当前 debug 签名；不重新生成 |

正式渠道还需要原有 `ANDROID_RELEASE_*` 签名配置；本次不切换渠道。SSH 禁用交互、严格核对 host key，失败即停止，不静默跳过镜像配置。

## 每次发布步骤

1. 修改客户端、测试、内置逐版本日志；Name/Code/Tag 必须一致。本版 `0.2.16` / `30` / `v0.2.16`。
2. 本地验证、生成体验 APK → push 主题分支 → 新 PR → 通知用户交给其他成员 review。未获确认不合并、不创建 Tag。
3. Review 和检查通过，运维确认镜像目录/HTTPS/权限/Secrets 后，由获授权成员按规范合并。**仅合并本 PR 不会发布 APK**；也不命中网站 `feat/**` 部署触发条件。
4. 在已合入且通过检查的提交上创建新 Tag，推送 `v0.2.16`。不移动历史 Tag、不手动上传 APK、不将 APK 进源码库。
5. `.github/workflows/android-release.yml` 验证 Tag 位于 main 历史、检查版本日志、测试发布事务、检查镜像配置、构建同一签名 APK、验证实际 APK 身份。
6. 生成三件制品：APK、`.apk.sha256`、`update.json`。清单主 `apkUrl` 指向自站，`apkFallbackUrls` 指向当前 Tag 的 GitHub 同包。只生成一份清单，两端字节一致。
7. 创建/恢复 GitHub 草稿 → 上传并回读三件制品 → SSH 上传到服务器隔离目录 → 验证哈希与身份 → 原子安装 `download/v0.2.16/` → 通过公网 HTTPS 再回读三件制品。
8. 再确认 versionCode 高于 GitHub latest → 公开 Release → 原子替换自站 `latest/update.json` → 公网回读核对。静态镜像不调用网站部署或数据库迁移。
9. 手机不经代理打开自站 JSON 和其中 APK URL，再验收 App 检查、确认下载、校验、系统安装、覆盖后保留数据。

目录结构如下：

```text
/srv/acmforever-releases/
├── download/v0.2.16/
│   ├── acmforever-0.2.16-debug.apk
│   ├── acmforever-0.2.16-debug.apk.sha256
│   └── update.json
└── latest/update.json
```

`.stage-*`、`.publish.lock`、`.update-*` 为私有事务文件，Nginx 不得公开。

## App 行为

启动第5步后台检查，默认开启自动检查，尊重已有关闭设置及六小时间隔。主清单发生连接/HTTP错误才读备用；身份/格式异常直接报错，不伪称已是最新版。自定义清单地址保持独立，不混入官方备用。

发现新版显示版本号、更新说明和等大的“下载安装包”“取消更新”（50%透明红色）按钮；点击下载进入猫娘加载页。无新版的手动检查显示“已是最新版本”和“确认”。没有 Wi-Fi 自动下载。

系统下载断线可续传；有网络但连续30秒无进度或下载源失败时尝试下一个 HTTPS 地址，离线等待网络。空间/设备错误直接提示；所有源耗尽后可手动重试。取消会移除任务并使迟到校验失效。恢复任务仍校验所属清单与来源索引。只有校验 SHA-256、大小、包名、更高版本、系统要求、当前安装证书后才交系统安装器。

旧0.2.15仍从 GitHub 取清单；本次自站就绪后需要手动分发一次0.2.16，或先用可访问 GitHub 的网络升级。0.2.16起默认自站优先。不能远程改变旧 APK 写死的清单 URL。

## 故障恢复与验收边界

- 上传/回读/镜像 stage 失败：GitHub保持草稿，自站 latest不变；不公开不完整版本。
- GitHub已公开但镜像 promote失败：Action报失败；自站可能仍为上一版。修复权限/网络/CDN后，使用**完全相同的三件制品**恢复同Tag发布步骤；脚本核对已公开制品后补stage/promote。重跑若重新编译得到不同字节则拒绝覆盖，应恢复原制品或发更高版本。
- 已公开Tag/已镜像版本不可换包；历史Tag不能回写latest，versionCode不得回退；同渠道证书不能改变。
- 新版自身有缺陷：发更高versionCode的修复版，不能把旧低版本伪装成更新。
- SSH/HTTPS验证、目录事务、草稿回读在本地有故障注入测试；生产SSH、Nginx和真实手机覆盖安装仍需运维/用户验收，不能用本地测试替代。

跨人 review 重点：发布顺序与中断恢复、SSH与路径约束、CDN缓存、APK哈希/签名、更新取消恢复。原讨论见 [PR #100](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/100)，现有发布基础见 [GitHub Tag发布](android-tag-release-v0.2.14.md)。

## 拆分后的验证与合并条件

原独立分支已有51项发布故障注入测试、71项Android单元测试通过；Lint 0错误/53条警告，debug应用和测试包构建成功；mirrorupdates和startupupdates两组模拟器回归通过。本次域名调整后的验证单独记录在 [Funnel 下载运维](android-funnel-mirror-operations.md)。仍需跨人review和手机实际更新验证；不能用首页200代替完整文件回读验收。

镜像传输、事务和校验逻辑沿用原#100。当前调整默认下载域名、相应回归测试和运维说明；新机上传目录、账号及Actions Secrets名称保持不变。
