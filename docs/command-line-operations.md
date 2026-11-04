# 网站与数据库命令行操作

目前已有服务管理、数据库初始化、只读查询、诊断、备份及恢复工具。账号创建、密码重置、帖子审核等业务操作通过管理后台或 HTTP API 完成，尚无统一的管理员 CLI。

## 服务器服务管理

仓库部署工作流通过公网 SSH 部署到 `root@118.178.192.81`，安装 **系统级 systemd 服务**。以 root 登录新服务器后执行以下命令；使用 `systemctl` 和 `journalctl`。首次部署、密钥配置及旧服务器迁移见 [新服务器部署说明](public-server-deployment.md)。

```sh
# 服务状态与最近日志
systemctl status acm-forever-webui.service --no-pager
journalctl -u acm-forever-webui.service -n 100 --no-pager

# 持续查看日志，Ctrl+C 结束查看
journalctl -u acm-forever-webui.service -f

# 启动、停止、重启：按需要分别执行
systemctl start acm-forever-webui.service
systemctl stop acm-forever-webui.service
systemctl restart acm-forever-webui.service

# HTTP 与数据库健康检查
curl --fail --show-error --max-time 5 http://127.0.0.1:8088/health
```

### 中文彩色实时日志

部署后，在服务器执行 `acm-logs -f`，可用中文查看登录成功/失败、接口访问、权限拒绝、后台任务开始/结束和服务器错误。绿色 `[INFO]` 表示正常记录，黄色 `[WARNING]` 表示请求受限或操作未完成，红色 `[ERROR]` 表示服务器或后台任务错误。终端自动启用颜色；重定向到文件时默认无颜色，也可通过 `--color always/never` 指定。

```sh
# 实时查看；开头解释全部字段，Ctrl+C 只退出查看
acm-logs -f

# 最近 30 分钟的警告及错误
acm-logs --since '30 minutes ago' --level warning -n 1000

# 每条请求后附字段说明，显示全部静态资源和轮询
acm-logs -f --all --explain

# 离线样例；每条都标明“演示”，不会产生网站操作
acm-logs --demo --color always
```

日志第一行说明“发生了什么”，第二行展示中文字段。`用户/身份` 来自本次请求已通过的认证；未检查身份的公开访问不会仅凭 Cookie 被标成已认证用户。`来源` 按网站既有可信代理规则解析，仍为 `127.0.0.1` 时只能确认代理地址。`请求` 使用路由模板，`<...>` 是参数占位符；`结果` 为 HTTP 状态码；`耗时` 统计处理至生成响应的时间，不含完整传输；`编号` 为服务端生成的请求 ID，也会返回在 `X-Request-ID` 响应头中。后台任务另有 `任务/任务编号`。错误会附 `错误类型/排查建议`，详细堆栈仍可用 `journalctl` 查看。

`202` 表示后台已受理，后续还应查看任务结束日志；`304` 表示继续使用浏览器缓存。默认收起成功的静态资源、健康检查和常见轮询，所有警告及错误仍显示。`-n` 统计读取的原始 journal 条数，过滤后实际显示数量可能更少。程序启动前的历史日志不会凭空补出登录人姓名；旧格式按其状态码和错误信息着色，作为原始诊断显示。

新事件不记录密码、Cookie、CSRF、Authorization、请求正文或 URL 查询参数，也不新增日志数据库表。账号名称、QQ、来源 IP 属于运维信息，只应向有日志权限的管理员开放。查看器会清理终端控制字符，并对旧日志中的常见凭据字段做尽力隐藏；这不能替代对原始历史日志的访问控制。正常请求由应用生成一条结构化记录，避免再重复输出 Hypercorn 原始访问行；异常堆栈保留。此查看器不修改服务和数据库。

完整源码仓库可运行 `python -m feat.api.acm_api.log_viewer --demo`。只有 `feat/` 的服务器部署可运行：

```sh
cd /root/acm-forever-feat
/root/acm-forever-data/venv/bin/python -m api.acm_api.log_viewer -f
```

仓库的部署默认值如下，实际路径与端口以服务器配置为准：

| 项目 | 默认位置 |
| --- | --- |
| 服务代码与工作目录 | `/root/acm-forever-feat` |
| Python | `/root/acm-forever-data/venv/bin/python` |
| 服务环境文件 | `/root/acm-forever-data/.env` |
| 数据库配置 | `ACM_DATABASE_PATH`，部署建议值为 `/root/acm-forever-data/acm_forever.db` |
| 监听地址 | `127.0.0.1:8088`，由 `ACM_API_HOST` / `ACM_API_PORT` 调整 |

`systemctl cat acm-forever-webui.service` 可查看实际的服务定义、工作目录和环境文件位置。服务环境文件不会自动加载到 SSH 终端；下面的数据库工具显式指定数据库路径。

## 查看数据库数据

需要安装 `sqlite3` 命令行工具。将示例路径替换成服务实际使用的 `ACM_DATABASE_PATH`，以只读模式打开：

```sh
sqlite3 -readonly /root/acm-forever-data/acm_forever.db
```

进入 SQLite 交互界面后，按需执行：

```sql
.headers on
.mode column
.tables
.schema forum_posts

-- 最近 20 篇帖子及审核状态
SELECT id, title, status
FROM forum_posts
ORDER BY id DESC
LIMIT 20;

-- Web 账号角色及启用状态
SELECT qq_id, role, is_active
FROM web_accounts
ORDER BY qq_id;

-- 各状态帖子数量
SELECT status, COUNT(*) AS count
FROM forum_posts
GROUP BY status;

.quit
```

这些查询面向服务的 SQLite 数据库。`tools/crawlers/` 单独生成的采集数据库不一定是网站正在使用的数据库；以服务的 `ACM_DATABASE_PATH` 为准。

## 数据库诊断与初始化

服务器只部署 `feat/` 的内容，因此在部署目录使用 `api.*` 模块路径：

```sh
cd /root/acm-forever-feat

# 只读诊断：数据库完整性、外键、图片引用及磁盘空间
/root/acm-forever-data/venv/bin/python -m api.acm_api.maintenance diagnose \
  --database /root/acm-forever-data/acm_forever.db

# 查看诊断、备份、校验和恢复子命令
/root/acm-forever-data/venv/bin/python -m api.acm_api.maintenance --help

# 需要补齐表结构时执行；保留已有数据，正常启动也会自动初始化
/root/acm-forever-data/venv/bin/python -m api.init_db \
  --database /root/acm-forever-data/acm_forever.db
```

若服务设置了 `ACM_MARKDOWN_UPLOAD_DIR`，诊断和备份也要传入对应的 `--markdown-dir /实际目录`。完整源码仓库根目录下，模块路径分别为 `feat.api.acm_api.maintenance` 和 `feat.api.init_db`。

## 备份与恢复

现有维护工具提供 `backup`、`verify`、`restore` 子命令，覆盖 SQLite、帖子图片与缩略图、Markdown/Wiki 图片及头像。具体停写、备份、校验和恢复演练步骤见 [备份与诊断文档](backup-and-diagnostics.md)。

备份前暂停所有写入者，再使用 `--writers-stopped`；数据库与图片需要一起保存。恢复工具写入新目录，核验后再调整服务配置使用恢复副本。

## 账号和帖子等业务管理

可以从命令行编写 HTTP 客户端，调用现有管理员 API。`/api/*` 使用登录 Cookie，写操作还需要登录响应中的 `csrf_token`，并通过 `X-CSRF-Token` 请求头提交。实际权限由服务器校验。

账号创建、启停、重置密码、角色修改和帖子审核的接口及会话调用示例见 [API 指南](api.md)。直接修改数据库不会执行接口中的会话失效、审核记录和关联数据处理，业务变更应通过这些接口完成。

## Windows 本地运行

在完整仓库根目录，先按 [API 服务说明](../feat/api/README.md#本地启动) 安装依赖，再构建前端并启动 API。以下命令分别在两个 PowerShell 终端执行：

```powershell
# 前端终端，从仓库根目录开始
cd feat/web
pnpm install --frozen-lockfile
pnpm build
```

```powershell
# API 终端，从仓库根目录开始
cd feat
.\.venv\Scripts\Activate.ps1
$env:ACM_WEBUI_SECRET_KEY = python -c "import secrets; print(secrets.token_urlsafe(48))"
$env:ACM_DATABASE_PATH = '.\data\acm_forever.db'
python -m api
```

访问 `http://127.0.0.1:8088`，在 API 终端按 Ctrl+C 停止服务。使用 `pnpm dev` 时，Vite 默认在 `5173` 提供前端开发页面；API 仍需单独运行。
