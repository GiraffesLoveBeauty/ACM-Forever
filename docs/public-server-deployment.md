# 新服务器部署与数据迁移

工作流 `.github/workflows/sync-feat-to-server.yml` 通过公网 SSH 连接 `root@118.178.192.81:22`，不再使用 Tailscale。网站使用系统级 systemd 服务。

| 项目 | 新服务器路径 |
| --- | --- |
| 代码及前端构建产物 | `/root/acm-forever-feat` |
| Python 虚拟环境 | `/root/acm-forever-data/venv` |
| 服务配置 | `/root/acm-forever-data/.env` |
| systemd unit | `/etc/systemd/system/acm-forever-webui.service` |
| 默认监听 | `127.0.0.1:8088` |

代码部署目录会被替换。数据库、上传文件和 `.env` 必须存放在代码目录以外。工作流只更新代码、依赖和服务定义，不负责搬运旧服务器的数据或配置。

## 1. 新服务器准备

2026-11-04 只读检查确认新机为 Ubuntu 26.04.1 LTS、x86_64、Python 3.14.4；已有 curl、tar 和 systemd，但缺少 ensurepip。以 root 执行：

```sh
apt-get update
apt-get install -y python3-venv curl tar
python3 -c 'import venv, ensurepip; print(ensurepip.version())'
```

前端在 GitHub Runner 上使用 Node.js 22 和 pnpm 构建，新服务器不需要安装 Node.js。安全组和系统防火墙需允许 GitHub Runner 连接 TCP 22。后续对外网站通过反向代理提供 80/443，8088 保持本机监听。

## 2. SSH 与 GitHub Secrets

Actions 需要有一把公钥已授权给 root 的 SSH 私钥。可以复用已经确认能登录新机的部署密钥，或单独创建 Actions 部署密钥。公钥追加到新机 `/root/.ssh/authorized_keys`，保留已有公钥；私钥只存入 GitHub Secrets，不提交代码或粘贴到聊天。

在仓库 **Settings → Secrets and variables → Actions** 配置：

| Secret | 内容 |
| --- | --- |
| `ACM_FOREVER_SERVER_SSH_KEY` | 对应已授权公钥的完整私钥，包含 BEGIN/END 行；此工作流使用无口令部署密钥 |
| `ACM_FOREVER_SERVER_FINGERPRINT` | 当前部署客户端使用的服务器 ECDSA host key 的 `SHA256:…` 指纹 |

在已可信登录的服务器终端读取 host key 指纹：

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ecdsa_key.pub -E sha256
```

仅复制输出中的 `SHA256:…` 字段。该服务器同时提供 RSA、ECDSA 和 ED25519 主机密钥；当前固定版本的部署组件与其协商 ECDSA，因此不能直接使用本地 OpenSSH 登录时看到的 ED25519 指纹。上传和远程执行两步都校验这个指纹；更换服务器密钥或部署组件版本时应重新核验。`TS_AUTHKEY` 不再被此工作流使用；若其他工作流仍引用，按其需要保留。

## 3. 首次部署代码，暂不启动

打开 **Actions → Sync feat directory to server → Run workflow**，选择包含本次修改的分支，保持 **start_service 未勾选**。

工作流会构建前端、上传代码、创建 Python 虚拟环境、安装依赖和系统级 unit，明确跳过服务启动。这一步不要求 `.env` 已存在，不初始化业务数据库。该模式仅用于尚未运行网站的新机；如果系统级服务正在运行，工作流会拒绝，以免在不重启服务的情况下替换代码。

## 4. 搬迁数据库、图片及配置

按 [备份与诊断说明](backup-and-diagnostics.md)，在旧服务器实际运行用户下暂停所有写入者，再制作并校验最终备份。旧机可能仍使用 WYJ 的用户级服务，应以旧机实际 unit 为准。不要直接把新机的 root/systemctl 命令套到旧机。

将可信备份目录传到新机，例如 `/root/acm-migration-snapshot`，同时单独传输旧 `.env`。数据库、帖子图片、缩略图、Markdown/Wiki 图片和头像必须使用同一份快照；Python 虚拟环境在新机重建，不复制旧 venv。

完成第 3 步后，在新服务器执行：

```sh
cd /root/acm-forever-feat
/root/acm-forever-data/venv/bin/python -m api.acm_api.maintenance verify /root/acm-migration-snapshot
/root/acm-forever-data/venv/bin/python -m api.acm_api.maintenance restore \
  /root/acm-migration-snapshot \
  --destination /root/acm-forever-data/restored
/root/acm-forever-data/venv/bin/python -m api.acm_api.maintenance diagnose \
  --database /root/acm-forever-data/restored/database.sqlite3
```

`restored` 必须是尚不存在的新目录。恢复结果包含 `database.sqlite3` 和 `uploads/{forum,markdown,avatars}`。核验通过后，将旧配置放到 `/root/acm-forever-data/.env`，保留所需服务密钥和 OJ 配置，调整路径：

```dotenv
ACM_API_HOST=127.0.0.1
ACM_API_PORT=8088
ACM_DATABASE_PATH=/root/acm-forever-data/restored/database.sqlite3
ACM_MARKDOWN_UPLOAD_DIR=/root/acm-forever-data/restored/uploads/markdown
```

域名、允许来源、代理信任及 Secure Cookie 按实际 HTTPS 入口配置；不要直接使用开发环境的示例配置。确认没有残留 `/home/WYJ/…` 数据路径。配置权限：

```sh
chmod 600 /root/acm-forever-data/.env
```

只有配置和最终数据都准备好后才启动，避免误用空数据库。最终快照后保持旧站停止写入，直到切换完成，避免两边数据分叉。

## 5. 启动、验收和域名切换

再次手动运行工作流，勾选 **start_service**。此时 `.env` 必须存在且非空；缺少配置会明确报错。工作流安装并启用系统服务，重启后检查 `127.0.0.1:8088/health`。

```sh
systemctl status acm-forever-webui.service --no-pager
journalctl -u acm-forever-webui.service -n 100 --no-pager
curl --fail --show-error http://127.0.0.1:8088/health
```

核对登录、账号与帖子数量、帖子图片、Wiki、题库和管理中心。配置新机的 HTTPS 反向代理并验收后，再将公网域名指向 `118.178.192.81`。继续使用 Tailscale 域名或 Bot 客户端时，其入口需另行调整；部署工作流不会自动迁移它们。

合入 main 后，命中工作流路径的 push 会正常部署并启动服务。手动运行默认不启动，日常手动更新运行中的站点应勾选 start_service。源码替换前会保存上一个代码目录，失败时该备份保留；数据库与上传目录不随代码替换或自动回滚。数据恢复和账号生命周期要求仍按备份文档执行。

常用服务命令与数据库操作见 [命令行操作说明](command-line-operations.md)。
