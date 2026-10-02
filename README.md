# ACM-Forever

面向本校 ACM 学习与交流平台的工程代码仓库。

项目讨论、会议纪要和需求文档保存在 [CJLUACM-DLC 文档仓库](https://github.com/GiraffesLoveBeauty/CJLUACM-DLC)。

## 目录与部署

- `feat/`：平台功能文件。合并到 `main` 后，此目录变更会由 GitHub Actions 镜像同步到服务器的 `/home/WYJ/acm-forever-feat`。
- 接收目录独立于现有梓喵部署目录；同步只更新文件，不重启其他服务。
- Actions 需要仓库 Secrets：`TS_AUTHKEY` 和 `ACM_FOREVER_SERVER_SSH_KEY`。

后续开发使用主题分支，并通过 PR 合并到 `main`。
