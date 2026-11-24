# Gitee 镜像诊断与独立恢复

日期：2026-11-24。状态：本 PR 实现，待外部 Review 和真实上传验收。Gitee v1.0.2 尚未完成，本文件不是发布成功记录。

## 故障与恢复入口

v1.0.2 在 GitHub 已公开八份制品；Gitee 已有五份，缺猫娘素材和两份清单。旧上传脚本隐藏了底层异常，重跑旧 Tag 也不会使用 main 的新工具。

[gitee_mirror.py（独立恢复）](../Android_APP/tools/gitee_mirror.py) 和 [gitee_transport.py（有界传输）](../Android_APP/tools/gitee_transport.py) 保留八附件、源码、固定证书与摘要门禁，不重新编译或覆盖 GitHub 首发文件。App 版本不在此 PR 修改。

恢复步骤：

1. 本 PR 交用户安排 Review，确认后合入 main。
2. Actions 打开 [Recover Gitee Android mirror](../.github/workflows/android-gitee-mirror.yml)，选择 main，输入现有 `v1.0.2`。使用已有 `GITEE_RELEASE_TOKEN` Secret；不在输入框或聊天填写令牌。
3. 使用当前已审工具读取目标旧 Tag 的版本和历史数据；验证 Tag 属于 main、GitHub 正式 Release 的源码标记与真实 Tag 一致，下载原始八附件。
4. 校验原件大小和摘要、APK 内置历史与 Review 快照，并用 JDK 复核基础 APK 和四模块的 JAR/v1 签名及固定证书。Android 完整签名在首发构建时验证，此处不重新制作文件，不需要签名私钥或 Android SDK。
5. 已有 Gitee 附件校验后复用，只上传缺失文件。全部八附件匿名回读正确、且没有更高正式版本出现，才解除预发布。
6. 检查 Gitee `prerelease=false`、App 实际入口及两份清单、APK 和四模块。真实上传及手机端验收通过后才能宣布发布成功。

不能移动旧 Tag 或覆盖已公开附件；不能改 main 后仅重跑旧 Tag。独立入口解决旧 Tag 下工具版本固定的问题。手动恢复仅允许 main，正常 Tag 推送仅允许匹配的正式 Tag。

## 超时、恢复和凭据

- 使用 runner 自带 curl，命令行只含 `curl -q --config -`。凭据经 stdin 或受控临时请求文件传入，不记录配置、请求体、认证头、响应正文、签名重定向 URL 或 curl stderr。禁用默认 curl 配置与隐式代理，保留 TLS 验证。
- 日志只输出文件名、数值耗时、发送字节、curl 错误码和经过限制的请求 ID。连接/TLS/首字节指标不是所有故障阶段的精确还原。另有无凭据 runner DNS/TCP/TLS 探针。
- 连接上限 15 秒、上传总期限至多 180 秒；单次匿名回读包含重定向与暂态重试共用 60 秒。Gitee 操作共享 15 分钟预算，工作流上限 20 分钟。
- GET 暂态错误有界重试；退避带抖动并尊重数字或 HTTP 日期 Retry-After。上传至多 3 次（含首次），只对明确未发送或明确限流拒绝的情况，回查后允许重试。
- 上传可能已送达时先有界回查。同名文件正确则复用；仍无法判断就停止，不盲目重复 POST。重复附件、错误摘要/身份、401/403/413 均停止，不自动删除或覆盖。
- 只提供文件级恢复，不声称支持 Gitee 未公开提供的分片续传。认证请求不跟随重定向；匿名回读每一跳均限制现有 Gitee/CDN HTTPS 白名单。

## 正常发布与权限

[Tag 工作流](../.github/workflows/android-release.yml) 将 GitHub 构建与 Gitee 镜像拆为独立 job。仅 `GITEE_MIRROR_MODE=automatic` 自动启动镜像；Gitee 凭据错误使镜像 job 失败，不再阻止 GitHub 正式包公开。manual 行为保持。

手动恢复是维护者明确请求的镜像操作，不受 automatic/manual 变量限制。两工作流共用 `android-tag-release` 并发组，也与历史 Tag 工作流串行。恢复的 GitHub 权限仅 `contents: read`；Gitee Secret 只交给镜像步骤，不交给 PR 测试、App 或不可信分支。

Gitee `latest` 是最后更新的 Release，会包含预发布。恢复工具分页检查正式版本，避免未完成版本遮挡回退保护；App 的对应修复另开客户端 PR。

## 验证边界

本地契约回归包括丢失上传响应、未发送失败、结果不明停止、错误文件与权限、预算、凭据脱敏、预发布过滤、发布前出现更高版本、主线已升级时仍使用目标 Tag 数据。工作流以 actionlint 检查。

实际验证：发布契约 100 项通过，无失败或跳过；actionlint 1.7.7 检查三个相关工作流通过；已公开的 v1.0.2 基础 APK 和四模块通过新增恢复路径使用的固定证书 JAR/v1 复核。

新传输已匿名读取 Gitee 元数据，并经两次受限重定向下载已存在的 v1.0.2 主 APK，SHA-256 与 GitHub 原件一致。此只读测试不能代替 GitHub runner 的真实上传验收。本 PR 不触发恢复或创建 Release；Review 后再按上述步骤验收。

若新增远端诊断确认托管 runner 到 Gitee 持续不可用，再单独评审受控国内镜像执行器；不默认新增服务器或让未经审核的代理接触令牌。
