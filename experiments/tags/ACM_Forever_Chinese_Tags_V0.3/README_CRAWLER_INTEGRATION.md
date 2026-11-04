# 爬虫导出到增量规划：离线联调

`check_crawler_integration.py` 复用现有输入适配器和 `Planner`，只读取明确指定的本地 JSON/JSONL 及持久目录。
默认不写文件；没有执行 AI、联网采集或连接 SQLite 的选项，也不加载 `.env`。

## 输入与检查范围

支持现有规范题目、SQL 行结构的 JSON、后端已解码记录，以及旧交接包 `statement.markdown` / `tags.values`。
本地 AtCoder 内容导出也使用现有适配器；`sha256` 保留为原始下载哈希，不能替代规范正文或 API 输入哈希。

每个文件默认选取 3 条可检查记录，校验身份、原始标签、源记录不变、重复适配、规范 JSON 往返和独立任务哈希。
有可信 Markdown 时检查其全文在规范正文中保留，包含其中的样例、代码和公式；这不能证明上游采集文本本身完整、公式语义正确或具有转载授权。
旧交接包的样例嵌在 Markdown 中，结构化 `sample_count=0` 不表示原题没有样例，也不声称已解析成结构化样例。

存在本机 `data/selection_manifest.json` 时，仅读取其中的留出身份，选样前排除；不读取留出题面或人工答案文件。
直接指定名称含 `holdout` / `gold_template` 的文件会在读取前拒绝。没有分组清单时报告 `manifest_found=false`，使用者需提供已确认可用于联调的文件。
合成样本不会被工具自动标记为真实数据；报告中的来源路径和 SHA-256 用于追溯，数据来源仍需人为核实。

## PowerShell

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'

# 默认只读；下列是真实本地交接包，不是新版数据库完整导出。
.\.venv\Scripts\python.exe -B -X utf8 check_crawler_integration.py `
  --input 'D:\ACM Project\DATA\contextpy_data_handoff_20261009\data\codeforces.json' `
  --input 'D:\ACM Project\DATA\contextpy_data_handoff_20261009\data\atcoder.json' `
  --limit-per-file 3

# 可选增加参数保存无正文的审计报告，文件名必须全新：
# --report outputs/plans/crawler-integration-new.json
```

`--data-root` 可显式指定隔离的持久目录。报告同时给出抽查输入和当前已持久化题目的独立标签/翻译计划。
计划里的 `needs_ai` 只表示将来需要授权的任务；报告本身不能作为安全执行器的真实请求绑定计划。
真实执行仍需独立的模型参数绑定计划及明确授权，不能直接把本工具报告交给执行器。

报告复用现有原子发布函数，只允许保存到已忽略的 `outputs/plans/` 下的新 JSON，不覆盖旧文件。
报告不包含完整题面、题解、原始 API 响应或认证配置。禁止将真实导出或报告强制提交 Git。

## 2026-10-30 验证边界

- 真实输入来源为 2026-10-09 交接包，CF / AtCoder 各 200 题；只对各 3 条非留出身份做适配与规划，不全量处理题库。
- 现有 10 道 ATC 的持久标签单独检查复用，不导入、重标或修改人工事件。
- 新版 `crawler_problems` 完整真实导出仍未取得；其字段及本地采集器输出形状通过合成数据、实际后端解析函数测试，不能冒称真实数据库联调完成。
- 原始交接包没有原始下载字节哈希时，`source_statement_sha256=null`，保留其既有 `content_hash`。
- 输入可适配不代表翻译一定可执行；双语版本完整性等仍由独立语言规划检查，待处理任务不会自动发送。
- 首轮候选抽查报告 `outputs/plans/crawler-integration-20261030.json` 在分组核对前包含一个留出身份，已被排除后的新版报告取代；该旧报告只保留审计，不作为验收证据。没有读取正式留出文件、调用 AI 或写入该题标签。
- 最终验收记录使用 `outputs/plans/crawler-integration-20261030-guarded.json`；测试与原始文件保护核验位于 `outputs/offline_integration_20261030/`。

## 后端仍需交接的内容

需要带稳定题号、完整正文、完整样例（含省略输出说明）、原始下载哈希、采集状态和语言的只读导出。
后续再约定解析器版本、增量更新水位、分页、来源权限及结果写回版本冲突协议。
本轮不修改爬虫、正式服务、数据库、词表、人工历史或旧缓存。
