# ACM-Forever

面向本校 ACM 学习与交流平台的工程代码仓库。

算法标签、翻译及本地题库验收的范围、启动与限制见 [题目二次处理交付说明](docs/algorithm-tagging-delivery.md)。

项目讨论、会议纪要和需求文档保存在 [CJLUACM-DLC 文档仓库](https://github.com/GiraffesLoveBeauty/CJLUACM-DLC)。

## 目录与部署

- `docs/`：工程协作规范与 API 调用说明。
- `tools/crawlers/`：题目元数据采集、AtCoder 题面与样例采集及 SQLite 入库工具，输出保存在被忽略的 `data/`。
- `feat/`：平台功能文件。合并到 `main` 后，此目录变更会由 GitHub Actions 镜像同步到服务器的 `/home/WYJ/acm-forever-feat`。
- `feat/api/` 包含独立 WebUI 与 API 服务，沿用原端口 `8088`。配置 `/home/WYJ/acm-forever-data/.env` 后，部署工作流会安装或更新用户级服务 `acm-forever-webui`。
- `feat/web/`：Vue 3 + Vite 前端，包含社区、个人中心和管理后台。开发端口 `5173`；生产构建由 API 服务在 `8088` 提供，Actions 部署前自动构建。
- `Android_APP/`：原生 Android 客户端、测试和历史浏览器原型；版本 Tag 触发 Actions 构建并将 APK 发布到 Release，安装包不提交源码 Git，签名材料仅在受控本机及 Actions Secrets 保管。
- 接收目录独立于梓喵部署目录，数据库和环境密钥保存在 `/home/WYJ/acm-forever-data`。
- Actions 需要仓库 Secrets：`TS_AUTHKEY` 和 `ACM_FOREVER_SERVER_SSH_KEY`。

后续开发使用主题分支，并通过 PR 合并到 `main`。

## 文档

- [issue-85-member-profile.md（成员资料筛选与可恢复编辑）](docs/issue-85-member-profile.md)

- [TCrB-AI项目工程规范.md（AI 项目工程协作规范 · 讨论稿）](docs/TCrB-AI项目工程规范.md)
- [api.md（API 调用指南）](docs/api.md)
- [android-app.md（Android v0.2.17、更新渠道、构建与发布）](docs/android-app.md)
- [android-v0.2.19.md（搜索拖拽、下拉刷新、便捷成员管理与主题分层 · 待评审）](docs/android-v0.2.19.md)
- [android-v0.2.18.md（搜索单列、官方主题适配与私人主题系统分享 · 待评审）](docs/android-v0.2.18.md)
- [android-v0.2.17.md（搜索历史、主题导入导出与独立App PR验收 · 待评审）](docs/android-v0.2.17.md)
- [android-theme-package-v1.md（本机主题包格式、原图与完整还原）](docs/android-theme-package-v1.md)
- [android-official-theme-adaptation-v0.2.17.md（官方主题源文件解析与直接采用范围）](docs/android-official-theme-adaptation-v0.2.17.md)
- [android-v0.2.16.md（原PR #100历史实现与测试记录）](docs/android-v0.2.16.md)
- [android-modification-standard.md（App修改标准、模块关联与缺失接口）](docs/android-modification-standard.md)
- [android-tag-release-v0.2.14.md（Android Tag 自动发布、签名配置与 App 更新）](docs/android-tag-release-v0.2.14.md)
- [android-release-fix-v0.2.15.md（草稿发布修复与重新首发 · 待评审）](docs/android-release-fix-v0.2.15.md)
- [android-release-api-plan-v0.2.14.md（已被 Tag 发布替代的自有服务器方案）](docs/android-release-api-plan-v0.2.14.md)
- [command-line-operations.md（网站服务管理、日志和数据库查询）](docs/command-line-operations.md)
- [backup-and-diagnostics.md（数据库与图片备份、诊断和恢复）](docs/backup-and-diagnostics.md)
- [forum-post-revisions.md（帖子修改、重投和版本冲突）](docs/forum-post-revisions.md)
- [markdown-code-blocks.md（代码高亮、字体和复制）](docs/markdown-code-blocks.md)
- [comment-markdown.md（评论 Markdown、公式和代码）](docs/comment-markdown.md)
- [README.md（Vue 前端开发与构建）](feat/web/README.md)
- [theme-development.md（个人主题开发与投稿规范）](docs/theme-development.md)
- [web-performance.md（Web 性能采样与加载验收）](docs/web-performance.md)
- [crawler-samples.md（采集命令、JSON 字段与 SQLite 入库）](docs/crawler-samples.md)
- [issue-52-member-training.md（普通成员训练闭环实施与验收）](docs/issue-52-member-training.md)
- [admin-account-import.md（Excel 批量开户操作说明）](docs/admin-account-import.md)
- [issue-84-account-import.md（Excel 批量开户与 OJ 资料导入设计及实施记录）](docs/issue-84-account-import.md)

- [wiki.md（Wiki 知识手册、共享 Markdown、接口与备份恢复）](docs/wiki.md)
- [issue-83-account-closure.md（账号注销、同 QQ 新建账号与发布验收）](docs/issue-83-account-closure.md)
