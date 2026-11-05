# Android 自有服务器安装包 API 方案（已替代）

状态：2026-11-05，历史设计摘要，未实施。用户和管理员已选择 GitHub Tag → Actions 构建 → Release 发布流程，当前以 [android-tag-release-v0.2.14.md（正式实施步骤）](android-tag-release-v0.2.14.md) 为准。

原方案拟在业务后端增加以下能力：

- `/api/mobile/v1/releases/latest?channel=debug|release`：公开更新清单。
- `/api/mobile/v1/releases/files/...`：固定版本 APK 下载与 Range 支持。
- 自有服务器持久化制品目录、SSH 上传、原子发布和回退 CLI。

这些后端接口、目录和发布工具均未新增，当前不作为待部署任务。原客户端已具备独立 HTTPS 清单覆盖选项，因此可直接改用 GitHub Release 公开附件，无需数据库或业务服务器改造。

当前 0.2.14 调试/正式客户端默认都使用公开仓库的 `releases/latest/download/update.json`；实际 APK、哈希、版本和说明由工作流生成。旧 debug 包首次迁移与签名配置要求见新的发布文档。
