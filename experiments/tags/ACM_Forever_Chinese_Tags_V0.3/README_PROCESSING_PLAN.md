# 阶段 7F：端到端离线验收与增量规划

本工具仅生成计划，不加载 `.env`、不构造 API 客户端、不连接数据库；没有 `--execute` 参数。
不会导入、改写、删除已有标签、人工事件、翻译、备份或请求缓存。
计划与 Demo 产物分别写到已有忽略规则覆盖的 `outputs/plans/` 和 `demo_generated/`。

## PowerShell 使用

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'

# 默认 dry-run：只读当前持久化的 10 题；预览首条独立任务和有效标签。
.\.venv\Scripts\python.exe -B -X utf8 plan_processing.py --from-persistent --preview 1

# 保存计划（不是执行 AI）；目标须为新文件，已有文件会拒绝覆盖。
.\.venv\Scripts\python.exe -B -X utf8 plan_processing.py --from-persistent --write --output outputs/plans/atcoder-10.json --preview 1

# 可共享的合成爬虫记录 → 统一适配 → 计划。先生成规范记录供人工检查。
.\.venv\Scripts\python.exe -B -X utf8 adapt_problems.py --input tests/fixtures/crawler_records.json --dry-run
.\.venv\Scripts\python.exe -B -X utf8 adapt_problems.py --input tests/fixtures/crawler_records.json --write --output outputs/adapted/demo-normalized.jsonl
.\.venv\Scripts\python.exe -B -X utf8 plan_processing.py --input outputs/adapted/demo-normalized.jsonl --dry-run

# 复用已有页面：同时实际运行阻断网络的全量测试并保存测试时间和源码摘要。
.\.venv\Scripts\python.exe -B -X utf8 demo_acceptance.py --run-tests
Start-Process -FilePath (Join-Path (Get-Location) 'demo_generated/index.html')
```

重复验收可使用默认 dry-run；需要保留另一份计划或规范输入时请换新文件名，避免覆盖旧记录。
`--data-root` 指定只读持久目录；`--cache-root` / `--manifest-root` 可重复指定已有证据目录。
不调用任何爬虫、网络导出接口或 SQLite；本阶段没有指定允许读取的测试数据库。
JSON / JSONL 使用现有 `read_problems` 与 `normalize`，不包含留出集处理逻辑。

## 计划协议与状态

每条记录包含 `problem_key`、原有 `content_hash`、重新核验的 `normalized_content_hash`、
独立 `annotation` / `translation` 任务、有效标签及来源、人工覆盖状态、原因和审核标记。
每项任务有 `input_semantic_hash`、`task_key`、策略版本/哈希、已有结果来源及 `needs_ai`。
计划不导出真实题面、题解、原始 API 响应、请求头或认证配置。

| 状态 | 意义 |
| --- | --- |
| reuse_existing | 两项任务均可复用或无需 AI |
| needs_annotation | 仅标签缺失，需要未来单独授权的标注任务 |
| needs_translation | 仅中文翻译缺失，需要未来单独授权的翻译任务 |
| needs_both | 两项都缺失，计为两个独立 API 任务 |
| needs_review | 内容改变、结果冲突、旧证据不全、请求投递状态不明等；受影响任务不自动重发 |
| pending | HTML / PDF / 空正文或语言不足以可靠处理 |
| invalid | 身份、规范记录、历史数据损坏或同一题目输入冲突 |

任务内部另有 `not_required`，用于中文无需翻译、CF 精确映射无需 AI 的情况。
整体状态只是汇总；例如标签待复核时，未受影响的缺失翻译仍可计为独立待处理任务。
`estimated_api_tasks` 只统计任务级 `needs_ai=true`，不包含被阻断的任务，绝不表示已执行。
Token 与费用无法可靠估算时为 `null`，不使用官方价格代替中转站账单。
内容变化时旧有效标签仍作为历史保留，但 `effective_tags_are_current_input=false`，不得当作新题面的确定结果。

## 语义复用与审计

- 标签输入：规范题目身份、题名、正文、原始 CF 标签集合、可用且经过验证的题解。
  不可用题解的 `missing/not_found/not_requested/unavailable/ambiguous` 仅在正文证据相同且旧输入哈希能够重建匹配时兼容。
- 翻译输入：身份、题名、语言判断以及实际选用的完整语言版本；不包含算法标签或题解。
  因此原始标签、题解、非选用语言版本的变化，不会无故重做已验证等价的翻译。
- 每项任务的提示词、Schema 和显式修订版本独立。标签还包含词表、CF 映射与规则版本。
  `--translation-revision` 的变化仅影响翻译，`--annotation-revision` 仅影响标签；有旧结果时转待核验，不擅自安排再次付费。
  实际提示词 / Schema 内容变化也会改变任务键，无需依赖源码路径。
- `task_key` 不包含绝对路径、输出路径、采集时间、难度或适配器源码哈希。
  同一输入重复规划、交换批次顺序，结果稳定；相同身份重复输入只计一次，冲突输入禁止出任务。
- 默认复用已有有效结果，不因服务商或模型不同而主动重标。保留原模型、原请求指纹、版本和代次作审计。
  `task_key` 是逻辑任务身份，不是将来某模型请求的完整计费指纹。
- 持久标签需通过现有标签合法性与人工覆盖查询，题面哈希校验、语义输入对比，以及原标签输入哈希绑定。
  人工删除不会因自动结果复用而恢复；完整人工确认优先，内容实质变化仍须复核。
- 老结果不含独立策略清单时，只读旧运行 manifest：核对 manifest 自身摘要、提示词、Schema、词表、映射和规则。
  不因其中适配器实现字节或路径变化而拒绝等价内容。若清单已丢失则待核验，不删除缓存“解决”问题。
  后续应把允许字段的语义策略元数据随持久结果归档，以解除对实验 outputs 清单的依赖；本阶段不改写旧结果。
- 仅有旧缓存时，必须校验原输入哈希、内容哈希、标签 ID 和语义策略；不同候选标签冲突则待核验。
- 翻译仅复用有效真实结果和可核验的策略。Mock、失败结果、只有旧版本号而缺少提示词依据的历史译文，不自动视作真实可复用结果。
- `sent/received/retry_wait/unknown_delivery/failed` 不自动重发。能定位题目时只阻断对应任务；
  无法定位题目的旧请求或损坏缓存，保守阻断该类任务并提示审计，标签和翻译互不混用。

## 写入安全

计划默认只输出摘要和预览。`--write` 仅可写 `outputs/plans/` 下的新 UTF-8 JSON。
拒绝越界路径、符号链接 / Windows 重解析点、敏感字段及已存在的目标。
先在同目录写完整临时文件并 `fsync`，再通过不覆盖目标的硬链接原子发布；失败时清理本次临时文件。
不支持原子发布的文件系统会报错，不降级为覆盖写入。

## 真实验证和 Mock 的边界

- 真实：已有 10 道 AtCoder 付费标注的持久记录、有效标签与人工状态，已有备份哈希和隔离恢复证据；本次只读复查。
- 真实旧输入：探索集中少量 CF / ATC 的身份、保留正文、标签与哈希稳定性检查。没有重新抓取原站，不能证明旧采集文本本身完整无损。
- 尚缺：新 `crawler_problems` 真实正文导出。本地没有发现可用的新采集 JSON/JSONL 或被明确指定的测试 SQLite。
  新结构到规范协议的联调仍使用 `tests/fixtures/crawler_records.json` 合成样本，不冒称真实爬虫联调。
- Mock：人工添加 / 删除 / 重置和英日文翻译在临时合成数据上真实执行模块逻辑；中文样本跳过。
  真实翻译仍为 0；Mock 不证明翻译质量。
- 离线全量测试阻断 socket 与真实 HTTP transport；测试记录绑定日期、源码、模板、样本及所依赖的后端 HTML 解析器。

## 五分钟团队演示

1. **0:00—0:45**：运行合成爬虫样本 dry-run，展示 CF/ATC 身份与 PDF 待处理分流，说明尚缺新爬虫真实导出。
2. **0:45—1:45**：运行 `plan_processing.py --from-persistent --preview 1`，展示 10 个旧标签复用、0 个标注任务、10 个翻译待处理任务，实际调用为 0。
3. **1:45—2:45**：打开 Demo「真实题目」和「增量计划」，按标签筛选、展开一题，关联自动标签、有效标签、模型来源与未人工确认状态。
4. **2:45—3:45**：隔离人工修正和撤销四步；查看英日文 Mock 翻译、公式代码保护与中文跳过，强调没有真实译文。
5. **3:45—5:00**：查看备份 SHA-256、10 题既有隔离恢复一致性，以及本次离线测试日期和源码匹配结果；说明 7G 安全执行器仅完成离线验证。

## 7G 安全执行集成与翻译准备

`annotate_api.py` / `translate_api.py` 的执行模式现统一进入安全执行器，真实执行还需要最新的模型参数绑定计划。
规划器本身仍然只读，不发请求。新稳定任务身份不使用旧执行器的路径或源码摘要。
以下安全措施已实现并通过离线测试，操作及剩余风险见 `README_SAFE_EXECUTION.md`：

1. 执行器强制读取并重新校验计划、当前代次与内容/策略，防止使用过期计划。
2. 给逻辑任务建立持久唯一索引和跨进程锁，先占用任务再发请求；重启时核对请求日志和已保存响应。
3. 独立请求指纹补充服务商、固定端点、模型、输出模式、输出 Token 参数及上限等实际请求参数。
   改变模型或请求参数只能在明确重标授权下执行，不能把旧任务误当成新缺失任务。
4. 对投递不明状态只允许人工查账 / 确认处理，不自动重发；完整响应已保存时优先本地解析恢复。
5. 将允许字段的提示词 / Schema / 输入语义和请求参数快照写入持久版本元数据，而非依赖实验 outputs；不要搬迁或删除旧缓存。
6. 首次翻译仅选择一题，确认完整英文版本、题面使用权限、模型接口和费用；约定 `limit=1`、重试 0、超时与输出上限。
   本阶段不读取凭据、不确认服务商能力，也不输出可误执行的付费命令。

需与后端同学确认：带 `statement_sha256`、采集状态、解析器版本、完整样例和可信链接的只读批量导出；
更新水位 / 稳定分页、题面语言与版权状态、PDF-only 分流，以及未来写回标签 / 译文的版本冲突协议。
当前不新增论坛表、不写正式数据库。
