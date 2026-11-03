# ACM-Forever

面向本校 ACM 学习与交流平台的工程代码仓库。

项目讨论、会议纪要和需求文档保存在 [CJLUACM-DLC 文档仓库](https://github.com/GiraffesLoveBeauty/CJLUACM-DLC)。

## 目录与部署

- `docs/`：工程协作规范与 API 调用说明。
- `tools/crawlers/`：题目元数据采集、AtCoder 题面与样例采集及 SQLite 入库工具，输出保存在被忽略的 `data/`。
- `feat/`：平台功能文件。合并到 `main` 后，此目录变更会由 GitHub Actions 镜像同步到服务器的 `/home/WYJ/acm-forever-feat`。
- `feat/api/` 包含独立 WebUI 与 API 服务，沿用原端口 `8088`。配置 `/home/WYJ/acm-forever-data/.env` 后，部署工作流会安装或更新用户级服务 `acm-forever-webui`。
- `feat/web/`：Vue 3 + Vite 前端，包含社区、个人中心和管理后台。开发端口 `5173`；生产构建由 API 服务在 `8088` 提供，Actions 部署前自动构建。
- 接收目录独立于梓喵部署目录，数据库和环境密钥保存在 `/home/WYJ/acm-forever-data`。
- Actions 需要仓库 Secrets：`TS_AUTHKEY` 和 `ACM_FOREVER_SERVER_SSH_KEY`。

后续开发使用主题分支，并通过 PR 合并到 `main`。

## 文档

- [TCrB-AI项目工程规范.md（AI 项目工程协作规范 · 讨论稿）](docs/TCrB-AI项目工程规范.md)
- [api.md（API 调用指南）](docs/api.md)
- [command-line-operations.md（网站服务管理、日志和数据库查询）](docs/command-line-operations.md)
- [backup-and-diagnostics.md（数据库与图片备份、诊断和恢复）](docs/backup-and-diagnostics.md)
- [markdown-code-blocks.md（代码高亮、字体和复制）](docs/markdown-code-blocks.md)
- [README.md（Vue 前端开发与构建）](feat/web/README.md)
- [theme-development.md（个人主题开发与投稿规范）](docs/theme-development.md)
- [crawler-samples.md（采集命令、JSON 字段与 SQLite 入库）](docs/crawler-samples.md)
- [issue-52-member-training.md（普通成员训练闭环实施与验收）](docs/issue-52-member-training.md)

- [wiki.md（Wiki 知识手册、共享 Markdown、接口与备份恢复）](docs/wiki.md)
- [issue-83-account-closure.md（账号注销与关联数据处理执行方案 · 草稿）](docs/issue-83-account-closure.md)
