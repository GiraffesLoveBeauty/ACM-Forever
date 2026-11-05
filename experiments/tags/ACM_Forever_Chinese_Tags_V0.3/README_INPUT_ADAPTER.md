# 阶段 7E：新题库离线输入适配

本阶段只处理本地 JSON/JSONL，不连接数据库、不下载页面、不标注、不翻译、不更改既有持久目录。
复用 V0.3 的 `prepare()` / `annotation_api.adapter.adapt()` 和后端 HTML 解析树。

## 实际题库结构

依据仓库中的 `feat/api/acm_api/problem_bank.sql`、`problem_bank.py`、`problem_sync.py`、
`problem_content.py`、`backend_api.py` 及 `tools/crawlers/`，表为 `crawler_problems`，共 24 个字段：

| 字段 | SQLite 类型 | 语义 |
| --- | --- | --- |
| platform / problem_id | TEXT NOT NULL，联合主键 | OJ 与原爬虫题号 |
| contest_id | TEXT NOT NULL | 比赛 ID |
| problem_index | TEXT，可空 | CF 题序或 ATC 展示序号；ATC 身份使用任务 ID |
| problem_name | TEXT NOT NULL | 原题名 |
| problem_rating | INTEGER，可空 | 原始来源难度，不代表统一等级 |
| problem_url | TEXT NOT NULL | 原站题目 URL |
| tags | TEXT NOT NULL，默认 `[]` | JSON 字符串数组 |
| metadata_json | TEXT NOT NULL | 当前目录元数据对象的 JSON 序列化 |
| statement_html / statement_text | TEXT，可空 | 选定语言的正文 HTML / 由解析树生成的纯文本 |
| statement_pdf | BLOB，可空 | 原始 PDF 字节；不是文本或文件路径 |
| statement_language / requested_language | TEXT，可空 | 实际语言 / 请求语言 |
| samples | TEXT NOT NULL，默认 `[]` | JSON 数组；通常为 `index/input/output`，官方省略输出时为 `output:null` 加非空 `output_note` |
| sample_count | INTEGER NOT NULL，默认 0，非负 | 样例组数 |
| statement_source_url | TEXT，可空 | 实际下载地址，可能含语言查询参数 |
| statement_sha256 | TEXT，可空 | 下载响应原始字节的 SHA-256，包括完整 HTML 页或 PDF |
| statement_fetched_at | TEXT，可空 | 最近成功采集时间 |
| last_fetch_status | TEXT NOT NULL | `never` / `ok` / `failed` |
| last_attempt_at / last_error | TEXT，可空 | 最近尝试时间 / 错误 |
| created_at / updated_at | TEXT NOT NULL | 行创建 / 更新时间 |

后端在失败时会保留上次正文，因此“有正文”不代表最近采集成功。
`statement_text` 的生成会去掉 HTML 标记并修剪行缩进；不适合独自承载公式和样例格式。
目前没有独立的采集版本哈希、解析器版本号或元数据版本哈希；`updated_at` 也不是内容哈希。

后端已有受权限保护的单题 JSON 接口：`/problems/<platform>/<problem_id>` 和
`/me/problems/<platform>/<problem_id>`，以及独立 PDF 接口。
单题 JSON 会解码 tags/samples，并返回 `statement_format`、`content_available`；
但没有返回 `statement_sha256`、`problem_index`、`metadata_json` 等全部数据库列。
未发现完整题面与版本信息的批量 JSON 导出接口。

本地 `codeforces_sample.py` 导出 `cf_sample.json`，CF 题号为 `123A`，并支持 gym URL；
后端同步模块存为 `cf_123A`。`atcoder_sample.py` 导出 ATC 元数据与可选的 Problems 难度字段；
`atcoder_collect.py` 将正文、样例写入本地 SQLite，保存原始 HTML 缓存。
本入口可读取这些导出的元数据，但未采集正文时会待处理，不自行调用爬虫补全。

## 身份及输入格式

- CF：`cf_123A`、`123A`、`A`、规范键 `codeforces:123:A` 交叉校验后得到同一身份。
  复用实际元数据约束：题序为 1—3 个大写字母加 0—2 位数字，或 1—3 位纯数字。
  支持 A1、ZZZ99、历史数字题序、contest/gym/problemset URL。
  纯数字组合 ID 无法独立判断比赛边界，必须提供 contest_id、规范键或可信题目 URL。
- ATC：`problem_id` 为完整任务 ID；`problem_index="D"` 仅是展示序号。
  `abc475` + `abc475_d` → `atcoder:abc475:abc475_d`。
  兼容 `abc001_1`、AtCoder Problems 的 `id` 字段和历史不以比赛名开头的任务 ID。
  不从任务名前缀猜测比赛；缺少比赛时需要原题 URL 或规范键。
- 规范键、显式字段、metadata_json 和所有可识别原站题目链接互相校验。
  冲突拒绝，禁止按题名合并。已有持久身份和旧输入的 content_hash 保留。
- 输入支持数组、`{"problems":[...]}`、`{"items":[...]}`、单条题目对象及 JSONL。
  接受 SQL 中的 tags/samples JSON 字符串和 HTTP 已解码数组；metadata_json 仅作已知字段的回填。
  不导出其中任意认证配置或未知字段。
- 旧数据协议继续支持；仅有 legacy `statement_html` 而缺少新爬虫字段的旧输入继续保守地
  保持 `html_only` / `html_pending`，避免默默改变原有正文及缓存语义。
  新题库 HTML 记录则执行本阶段的结构转换。

## 正文与处理状态

优先转换 HTML（保留原始 HTML 与爬虫原始纯文本），避免使用较有损的纯文本列。
树解析器直接读取现有后端 `problem_content.py`；不加载正式服务、不运行采集器、不写后端字节缓存。
保留标题、段落、LaTeX、var、math/tex、上下标、链接、列表、简单表格、代码及样例空白。
十进制有序列表逐项计算原编号，支持 `ol[start]`、`ol[reversed]` 与 `li[value]`，包括跳号、重复、零和负数；无序列表仍使用项目符号。有序编号写成独立的 `3\.`、`7\.` 段落，页面显示为 `3.`、`7.`，防止 Markdown 引擎将跳号自动排成连续编号。数字前缀留在本地翻译结构中，不交由 AI 改写。
非法或重复编号属性、字母／罗马编号、显式 CSS 自定义计数、异常列表结构以及包含有序列表的嵌套层级会记录具体 issue 并进入 `html_pending`；保留原始 HTML 和已提取的文字，不默认为可靠题面。此修复不会重写已保存的题目或缓存；重新适配含编号的正文会因语义修正产生新的输入哈希，旧结果需按现有增量流程复核。
ATC 完整网页使用现有容器和语言选择规则，排除导航区域。
纯文本统一换行符；单独存储且正文中缺少的样例按序号补充为代码块，不压平缩进或空行。

| processing_status | 含义 |
| --- | --- |
| ready | 可用文本且未发现结构异常、明确失败采集等问题；不代表算法或译文已经验证 |
| html_pending | 图片依赖、MathML/已渲染公式、SVG/canvas/嵌入对象、复杂表格、错误页、损坏结构或无法确认正文完整 |
| pdf_pending | 有 PDF 元数据但无可靠文本；PDF 地址、文件名或二进制不会成为 API 正文 |
| missing_statement | 正文为空 |
| source_pending | 有正文，但最近采集 failed/never 或显式题面状态不可信 |

pending 记录通过现有 `statement_status != "ok"` 阻止进入标注/翻译正文流程。
身份、字段类型、样例计数或来源哈希错误记为 invalid。
同一批次相同身份、不同输入内容会阻止该身份输出；完全重复的数据只输出一条并合并来源链接/ID。
批次存在任何 invalid 时，`--write` 不发布部分输出。

### 特殊样例与本地内容导出补充

- `input` 必须为字符串，允许明确无输入时为 `""`；缺失字段不等于无输入。
- `output` 必须显式存在。字符串（包括空字符串）是实际样例输出；`null` 表示原站省略完整输出，必须同时提供非空字符串 `output_note`。
- `null` 原样保留，不转成 `"null"`、空字符串、说明文字或虚构答案。正文中用独立引用区块标明说明不是期望输出，不放入答案代码块。
- 样例序号为唯一正整数；样例排序与 CRLF 规范化稳定，保留代码缩进及空行。说明变化影响正文及标签/翻译输入哈希；仅换行符变化不影响这些哈希。
- JSON 再导入会校验样例形状及说明与正文的一致性。原有普通样例、旧身份和旧缓存不迁移、不改写。
- 本地 `atcoder_collect.py` 成功内容导出使用 `sha256`、`source_url`、`requested_language` 等字段；原始下载哈希 `sha256` 映射到 `source_statement_sha256`，与 SQL 的 `statement_sha256` 语义相同。多个原始哈希字段冲突时拒绝输入，不以规范正文哈希替代。
- 原始哈希缺失仍为 `null`；只有导出字段而没有原始下载字节时，不能宣称已独立校验下载哈希。

真实本地导出的只读抽查、留出身份排除及增量规划操作见 [README_CRAWLER_INTEGRATION.md](README_CRAWLER_INTEGRATION.md)。

## 哈希边界与兼容性

| 字段 | 计算或来源 |
| --- | --- |
| source_statement_sha256 | 原爬虫 statement_sha256，原始下载字节；缺失即 null，不从正文伪造 |
| source_content_hash | 新爬虫记录自带的其他 content_hash，独立保留，不用来替代规范哈希 |
| normalized_content_hash | 规范身份、题名、规范正文的确定性摘要 |
| content_hash | 新爬虫记录使用 normalized_content_hash；旧协议保留已有值，避免改写旧缓存语义 |
| verified_content_hash | 沿用现有 title/text/html 摘要，继续兼容持久化与备份校验 |
| annotation_input_hash | 复用现有 adapt() 的标签输入摘要，包含标签、题面状态及可靠题解证据 |
| translation_input_hash | 翻译所选题名、正文、语言与处理动作的摘要，不含凭据 |

后两项不是完整请求指纹：完整指纹还包括模型、服务商、提示词、Schema、词表和请求参数。
source 更新时间或下载字节哈希变化，正文不变时，规范/API 输入哈希保持稳定。
标签变更会改变标签输入哈希，但不自动改变翻译输入哈希。
本次加入 `input_adapter_version="crawler-input-1"`；导出的规范 JSONL 可幂等重读，并校验字段别名和哈希。

**付费缓存注意：** 本次对 `annotation_api/adapter.py` 做了 CF 显式数字题序的局部修正，
防止旧组合题号逻辑把合法题序当比赛前缀剥离。未修改请求指纹或缓存算法。
但现有 `profile_for()` 纳入整个输入文件及 `annotation_api` 源码哈希，因而本次更新会改变 profile。
旧缓存、原始预测和持久标签均保留；不能直接假定新版本 `--resume` 命中旧版本缓存。
重新启动付费任务前必须核验请求计划，优先复用已有持久结果。

后续需要单独设计逐题稳定输入缓存、旧请求状态迁移/索引及逐题增量导入；
保留 provider/model/schema/prompt/词表/参数维度，不丢弃 unknown_delivery 和人工覆盖。
翻译现有指纹仍包含 verified_content_hash，HTML 原始结构变化可能导致新翻译指纹；本阶段不改变这一策略。

## 标准输出示例

以下为脚本对合成文本题的实际摘要字段；完整输出还包含 rule_base、原始 HTML、样例、来源与审核相关字段：

```json
{
  "problem_key": "codeforces:123:A",
  "platform": "codeforces",
  "source_problem_id": "cf_123A",
  "problem_id": "A",
  "contest_id": "123",
  "original_title": "Mock Addition",
  "original_statement": "Add two integers.",
  "source_links": ["https://codeforces.com/contest/123/problem/A"],
  "raw_tags": [],
  "difficulty_raw": null,
  "source_statement_sha256": null,
  "content_hash": "1cf8b7418aa817e97226bf34e003dd45b1fb721f5649fbd97445dcb83d8b1678",
  "normalized_content_hash": "1cf8b7418aa817e97226bf34e003dd45b1fb721f5649fbd97445dcb83d8b1678",
  "annotation_input_hash": "8facbe3042bf8a818714c08c384bb0b2b3d5457501420012592f888942fc99b7",
  "translation_input_hash": "d40cbcc807ea6eaf419f6055e0060058cfa39e87c494603ad59815599e7ca97f",
  "statement_format": "text",
  "statement_status": "ok",
  "processing_status": "ready",
  "input_adapter_version": "crawler-input-1"
}
```

## PowerShell 使用

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'

# 默认只读预览；样本为合成数据，不含真实 OJ 题面。
.\.venv\Scripts\python.exe -B -X utf8 adapt_problems.py --input tests/fixtures/crawler_records.json --dry-run --preview 3

# 显式导出规范 JSONL；目标必须尚不存在，只能位于已忽略的 outputs/adapted/。
.\.venv\Scripts\python.exe -B -X utf8 adapt_problems.py --input tests/fixtures/crawler_records.json --write --output outputs/adapted/crawler_mock_v1.jsonl

# 对导出文件再次只读验证。
.\.venv\Scripts\python.exe -B -X utf8 adapt_problems.py --input outputs/adapted/crawler_mock_v1.jsonl --dry-run

# 回归测试，全为离线/Mock；不使用真实 Key。
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p 'test_*.py'
```

预览不展示完整题面；输出包含题面，仅存本地受忽略目录。
退出码：0 为无 invalid，1 为有 invalid，2 为文件/输出参数等整体错误。
`summary.invalid` 为错误记录数量，不是不同题目身份数量；pending 按实际细分状态统计。
没有 SQLite 参数，不会打开默认题库或正式数据库。

## 与后端确认及下一阶段准备

1. 提供离线、带 schema_version 的完整 JSONL 导出约定，包括比赛、任务/题序、来源链接、
   原始下载哈希、题面语言、采集状态及样例；确定分页/增量水位与删除事件语义。
2. PDF 导出使用 has_pdf 或独立元数据引用，不将 BLOB/认证下载 URL 混入正文；确认是否有可靠文本层。
3. 确认是否可以增加 crawler/parser 版本元数据；当前 updated_at 和原始响应哈希不能互换。
4. 明确 ATC Problems 原始难度与展示值的字段，保留 difficulty_source，不宣称跨 OJ 分数等价。
5. 真实翻译前筛选 ready、检查语言、公式图片与样例、核对题面展示/翻译授权，并保留原文。
6. 单独核验模型和参数、费用上限、缓存迁移及 unknown_delivery；批准后才允许单题真实调用。
7. 现阶段无需修改数据库；不执行已完成 10 道 ATC 的重标注、翻译或持久目录迁移。

仍不处理 PDF/OCR、图片语义、MathML/仅渲染公式还原、复杂布局、缺正文补采集及正式库增量写入。
