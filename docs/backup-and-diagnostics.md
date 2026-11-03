# Web 服务诊断、备份和恢复演练

工具只使用 Python 标准库，不启动应用、不执行数据库迁移。支持 SQLite（包含已提交的 WAL 事务）、帖子原图及缩略图、Markdown/Wiki 图片和头像。不会打包代码、`.env` 或服务器密钥。备份目录包含账号哈希和私有内容，应存于只有运维账号可读的目录，并按部署环境加密和异地保存。

以下命令从仓库根目录执行。数据库路径是示例，必须替换成正在使用的 `ACM_DATABASE_PATH`。工具要求显式传入数据库；不会猜测生产配置。若部署设置了 `ACM_MARKDOWN_UPLOAD_DIR`，`diagnose` 和 `backup` 都必须加 `--markdown-dir /实际目录`。头像、帖子目录与服务一致，取数据库旁的 `uploads/avatars`、`uploads/forum`。

仓库部署工作流安装的是 WYJ 的用户级服务，以下服务命令需以 WYJ 账号执行。若服务器只部署了 `feat/` 内容，在 `/home/WYJ/acm-forever-feat` 执行，将 `python -m feat.api.acm_api.maintenance` 替换为 `/home/WYJ/acm-forever-data/venv/bin/python -m api.acm_api.maintenance`。更多服务及数据库查询命令见 [命令行操作说明](command-line-operations.md)。

## 1. 只读检查和日志

```sh
python -m feat.api.acm_api.maintenance diagnose --database /home/WYJ/acm-forever-data/acm_forever.db
systemctl --user status acm-forever-webui --no-pager
journalctl --user -u acm-forever-webui --since '30 minutes ago' --no-pager
curl -f http://127.0.0.1:8088/health
df -h
```

服务名和监听端口以实际 systemd 配置为准。诊断输出 JSON，包括数据库完整性、外键异常数量、各类图片缺失数量和可用磁盘空间，不输出账号资料、正文、密码或令牌。退出码 0 表示通过，1 表示失败。在线诊断仅供排查；并发上传或删除可能造成暂时的引用检查差异，应在停写后复查。SQLite 只读连接会使用正常的 WAL 锁与共享内存机制，不对业务数据库执行写入或建表。

## 2. 先停写，再备份

SQLite 在线备份本身是一致的，但数据库和图片要同一时点，必须暂停所有写入者：Web 服务、Bot 和直接写库的脚本。仅暂停 Web 但 Bot 仍写同一个数据库是不够的。`--writers-stopped` 是操作员对停写状态的声明，工具无法替代服务管理器判断。

```sh
systemctl --user stop acm-forever-webui
# 如有共享此数据库的 Bot/脚本，同时停止它们。
python -m feat.api.acm_api.maintenance backup \
  --database /home/WYJ/acm-forever-data/acm_forever.db \
  --destination /home/WYJ/acm-backups/2026-11-02-001 \
  --writers-stopped
python -m feat.api.acm_api.maintenance verify /home/WYJ/acm-backups/2026-11-02-001
systemctl --user start acm-forever-webui
```

目标必须是全新的目录，且不能与数据目录或图片目录互相包含。源诊断不通过会拒绝备份。SQLite 通过 backup API 读取已提交 WAL，不直接复制正在使用的 `.db` 文件。快照转换成单文件数据库，图片逐文件复制，manifest 记录相对路径、大小和 SHA-256，完成后再次校验数据库和引用。

软链接、Windows junction、特殊文件和图片目录内非受管图片文件会被拒绝；请先检查实际存储布局。备份不会删除源文件。异常中断可能留下未完成的目标目录；缺少有效 manifest 的目录不能恢复，应保留用于排错并选择新的目标重试。命令失败后也要按实际情况恢复已暂停的服务。

## 3. 恢复到新目录并验证

```sh
python -m feat.api.acm_api.maintenance restore \
  /home/WYJ/acm-backups/2026-11-02-001 \
  --destination /home/WYJ/acm-restore-drill-001
python -m feat.api.acm_api.maintenance diagnose \
  --database /home/WYJ/acm-restore-drill-001/database.sqlite3
```

恢复在创建目标前校验快照，复制后再检查。目标若已存在会拒绝，不覆盖当前数据库。恢复后的结构为 `database.sqlite3` 和 `uploads/{forum,markdown,avatars}`，自定义 Markdown 存储也会归一到此结构。

如要让服务使用恢复副本，停写后将 `ACM_DATABASE_PATH` 指向新目录内的 `database.sqlite3`；如果原配置包含 `ACM_MARKDOWN_UPLOAD_DIR`，也需改为新目录内的 `uploads/markdown`。服务用户需要有新目录和文件的读写权限；工具默认新建目录为当前用户私有，Linux 可按部署账号调整所有权。保持原目录完整，以便回退。启动服务后验证 `/health`、登录、帖子、图片、Wiki 和管理中心，再恢复其他写入者。演练不应对正式数据库做覆盖恢复。

SHA-256 用于检测传输损坏和文件变动，manifest 本身没有签名。应使用可信备份来源并保护备份目录访问权限。恢复失败时可能留下部分复制的新目录，不能将失败目录用于启动服务。

## 本地验证

```sh
python -m unittest feat.api.tests.test_maintenance -v
```

覆盖 WAL 事务、图片往返、自定义 Markdown 目录、只读诊断、缺图/外键问题、损坏检测、禁止覆盖、路径穿越和链接拒绝。Windows 未开启符号链接权限时，对应测试会明确跳过；其他断言照常执行。工具不会替你连接或操作线上服务器。


## 账号注销后的备份与恢复

启用 Issue #83 注销前，运维需把可信备份的访问范围和最长 30 天保留措施落实并演练；本工具不自动删除外部备份。注销审计由应用按 180 天清理，最小墓碑为禁止重新开户和公共引用持续保留。

上述 restore 只恢复所选快照，不会自动获知快照之后的新注销。恢复前必须在维护状态保全最新数据库/WAL、closed 墓碑、epoch/凭据版本、注销审计和资源撤销/清理清单；恢复后由运维重放关闭与清理规则并核验，再更换会话密钥使旧 Cookie 失效，最后恢复流量。不能直接启用更早快照里的 active 账号。无法证明最新清单完整时保持登录、同步和写入关闭；代码回退也必须保留生命周期守卫。

资源已撤销后，数据库引用在同一事务清除，物理文件可由持久任务在备份/重启后继续清理；复制到备份中的待清理文件同样受备份访问权限与保留期限约束。新版本生成的包含 closed 状态的快照恢复后会继续保留墓碑及清理任务，但这不能替代快照之后注销清单的重放演练。
