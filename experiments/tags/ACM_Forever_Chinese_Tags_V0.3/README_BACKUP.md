# 阶段 7C：标签与翻译备份恢复

`backup_labels.py` 仅执行本地文件操作，不加载 `.env`，不实例化 API 客户端，不生成 AI 请求。复用 `Repository`、`TagManager`、`Journal` 校验持久目录、人工事件和有效标签。无需安装新依赖。

## 备份内容与路径

备份源默认是现有 `data/labels`（遵循 `TAG_DATA_ROOT`）。备份根默认由项目目录推导为其同级的 `<项目名>-Backups/labels`，没有硬编码 Windows 盘符；可通过 `TAG_BACKUP_ROOT` 或 `--backup-root` 指向另一块磁盘。禁止在 Git 仓库或源数据目录内创建备份。

网页人工修改还使用标签根目录旁的 `local_tag_management/overrides.jsonl`（默认即 `data/local_tag_management/overrides.jsonl`）。创建备份会自动检查并收集这个独立文件。若网页用 `ReadOnlyLabels(..., override_file=...)` 指定了其他路径，备份必须使用同一路径的 `--override-file` / `create_backup(..., override_file=...)`；显式指定的文件不存在时失败，避免拼错路径后静默漏备份。工具只读取该文件，不遍历其父目录，也不收集旁边的配置、锁或临时文件。

每次创建独立 UTC 时间戳加随机后缀的目录，不覆盖已有备份：

```text
<backup-root>/<UTC-timestamp>-<suffix>/
├── manifest.json
├── payload/
│   ├── annotations/*.jsonl                 # 自动标签全部原始记录
│   ├── catalog/current.json
│   ├── catalog/generations/<hash>/          # 所有目录快照、标签、版本清单
│   ├── manual/overrides.jsonl               # 如存在，完整人工事件链
│   ├── translations/current.json           # 如存在，译文版本指针
│   ├── translations/history/<hash>.json
│   ├── translations/activations/<hash>.json # 翻译发布审计与结果绑定
│   ├── translations/requests/<hash>.json    # 白名单处理后的请求状态
│   └── exports/                            # 已审查的 JSON/JSONL 导出
├── local_tag_management/overrides.jsonl     # 如存在，网页实际使用的完整人工历史
├── versions/
│   ├── tag_taxonomy_v0.3.json
│   ├── cf_mapping_v0.3.json
│   └── ai_annotation_prompt_v0.3.md
└── request_states/<cache-namespace>/<request-hash>.json
```

`manifest.json` 包含备份版本、创建时间、当前 generation、标签版本、题目/历史/翻译数量、每个文件的相对路径/字节数/SHA-256、总数量和大小、完整目录清单、有效标签视图摘要，以及被排除或筛选的记录列表。标签/映射/提示词副本用于验证版本依据，不修改项目词表。

新备份使用版本 2；清单的 `web_manual` 单独记录网页实际采用的历史来源、事件数和有效标签视图 SHA-256。网页覆盖文件存在时优先使用它，即使文件为空；文件不存在时才回退到 `payload/manual/overrides.jsonl`，与网页现有规则一致。两份历史分别保留原始字节，不拼接、不覆盖，也不会将人工删除的标签恢复为有效标签。校验使用网页相同的 `TagManager`，包含标签来源、人工状态和历史计数。

版本 1 备份仍可校验和隔离恢复，但只代表旧备份中已记录的内容完整；返回 `web_manual_verified=false` 和明确警告，不能据此确认包含网页人工历史。旧备份无法补回从未保存的事件，请在原文件仍存在时重新创建版本 2 备份。

不备份锁文件、原子写入临时文件；遇到未审查文件、未知目录、敏感字段或疑似认证字符串时拒绝创建备份。`.env`、Key、认证头、虚拟环境不在允许路径内。原始标签、目录、人工历史、翻译历史和导出保持字节一致；请求状态是唯一进行字段筛选的记录。

## 请求状态字段白名单

允许保留：`state`、规范题目身份、64 位指纹/profile ID、已知错误码、数值 HTTP 状态/耗时、`fatal` 布尔值、三项非负整数 Token 统计，以及每次尝试的受控状态和统计。响应只保留用量统计。不复制原始响应正文、Key、配置、认证头、异常文本、任意响应扩展字段或完整缓存预测副本；预测已保存在持久标签记录中。未知错误文本转换为固定的 `redacted_error`。

默认 CLI 从实验 `cache/` 收集标注请求状态。`--request-root` 可指定另一请求目录；`--no-annotation-requests` 表示明确不收集实验请求状态。Python 函数 `create_backup(..., request_root=...)` 需要显式传入。翻译请求状态随持久目录自动备份。

`sent`、`received`、`retry_wait`、`unknown_delivery` 均不会改成可重试状态。隔离恢复后的翻译请求记录会继续阻止重复发送。`request_states` 是防重放审计记录，**不是可直接放回实验 `cache/` 的可执行缓存**，因为原始响应正文已被有意排除。未来若重启实验标注，需要单独设计请求记录迁移及检查；本工具不会重建实验缓存或自动继续付费标注。

## PowerShell 使用

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'

# 创建并自动验证；也可以 --backup-root 指向另一块磁盘
.\.venv\Scripts\python.exe -B -X utf8 backup_labels.py create

# 网页使用自定义覆盖文件时，显式指定同一个文件；以下变量填实际路径
# .\.venv\Scripts\python.exe -B -X utf8 backup_labels.py create --override-file $websiteOverrides

# 将实际返回的时间戳目录填入变量
$labelsBackup = 'D:\ACM Project\ACM-Forever-Backups\labels\<实际备份目录>'
.\.venv\Scripts\python.exe -B -X utf8 backup_labels.py verify $labelsBackup
.\.venv\Scripts\python.exe -B -X utf8 backup_labels.py summary $labelsBackup
.\.venv\Scripts\python.exe -B -X utf8 backup_labels.py list

# 目标必须不存在；恢复前先验证全部清单和哈希
$isolatedRestore = 'D:\ACM Project\ACM-Forever-Backups\isolated\<新的隔离目录>'
.\.venv\Scripts\python.exe -B -X utf8 backup_labels.py restore $labelsBackup --destination $isolatedRestore
```

`restore` 返回 `restored_data_root=<隔离目录>/payload`，以及 `restored_override_file=<隔离目录>/local_tag_management/overrides.jsonl`（没有网页覆盖文件时为 `null`）。同一备份恢复的两个路径必须一起使用，不能只复制 `payload` 后丢弃其旁边的网页历史。工具恢复后主动重载标签，并以 `web_manual` 核对网页有效标签摘要；不会更新环境变量或当前正式目录指针。

网页可通过 `ReadOnlyLabels(restored_data_root)` 自动发现旁边恢复出的覆盖文件，或显式传入 `override_file=restored_override_file`。直接使用 `Repository(...).manager()` 仍只读取目录内的独立人工历史，不能代替网页视图。需要保护位于其他位置的活动覆盖文件时，恢复命令可额外传 `--active-override-file $websiteOverrides`；恢复始终只写全新的隔离目录，不替换正在使用的数据。

指定备份中的历史自动标签目录可附加 `--generation <64位generation_id>`。此操作只改变新隔离目录的版本指针，并完整保留该备份所有历史及人工事件，不把人工删除过的标签恢复为自动有效。人工锚点与旧题面不一致时，沿用既有 `needs_review` 状态。后来的译文保留在历史中；哈希不匹配的译文不会用于旧题面展示。若需恢复某一时间点的完整人工状态，选择该时间点创建的独立备份。

## 完整性与失败行为

创建前验证所有 generation、题目与标签身份/哈希、两份人工事件链、译文索引。创建前后对源目录文件字节、目录清单及外部网页覆盖文件的内容和存在状态进行乐观一致性检查；发现并发变化即报告失败。外部文件同样执行敏感字段、题目关联和符号链接/重解析点检查。创建/恢复期间应暂停导入、人工修改和翻译写入，本工具不会创建或修改源锁文件。清单最后写入，未完成目录不会通过校验；失败后的新目录保留以供检查，不自动删除。

恢复拒绝已有目标、活动目录及其内外嵌套目标、路径穿越、盘符/ADS/Windows 设备路径、大小写别名、符号链接/junction/reparse point、清单外文件及缺失文件。目标写入使用独占创建，复制已校验的内存快照，再核对所有字节和有效标签。备份词表、映射和提示词必须与正在运行的工具版本一致，避免跨版本静默转换。

数据结构升级需先显式扩展路径和请求白名单。当前工具将全量字节加载内存，适用于本阶段数据量；大规模译文/HTML 数据可在后续增加受锁保护的流式快照。SHA-256 能检查损坏，不能替代数字签名或访问权限。备份没有加密；请保护备份目录并另存一份到其他磁盘。与源数据位于同一磁盘的备份不能防范磁盘故障。异常断电时部分新目录可能留下，校验不会将其视为可恢复备份。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
```

测试仅写临时模拟数据，覆盖完整/重复备份、损坏/缺失检测、人工纠错和撤销、版本及翻译恢复、未知投递阻断、敏感请求筛选、非法路径、链接和已存在目标拒绝、并发变化检测与查询一致性。Windows 重解析点检查使用模拟文件属性，不需要管理员创建链接。

正式数据目录切换仍需另行设计显式确认流程，本阶段没有提供生产覆盖操作。
