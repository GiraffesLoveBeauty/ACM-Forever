# 爬虫采集、JSON 字段与 SQLite 入库

当前提供 Codeforces 和 AtCoder 元数据采集工具，以及 AtCoder 题面、样例采集和 SQLite 入库工具。本地数据库默认位于 `data/problem_bank.db`，供采集暂存；管理员也可通过服务端接口直接抓取新的 AtCoder 或 Codeforces 题目，写入 `ACM_DATABASE_PATH` 指定的服务端数据库，详见 [API 调用指南](api.md#管理员采集新题目)。本地脚本仅使用 Python 标准库，无需安装数据库服务或第三方依赖。

## Codeforces 采集

使用 Python 3，仅依赖标准库，无需安装 API 服务依赖。`-X utf8` 保证 Windows 下中文输出采用 UTF-8。在仓库根目录运行：

```powershell
python -X utf8 tools/crawlers/codeforces_sample.py
```

默认访问公开的 `problemset.problems` 接口一次，下载完整元数据，再导出最多 20 道可定位的编程题。它保持接口返回顺序，不按年份筛选。`--limit` 只限制导出数量，不减少 API 下载量。

输出固定在仓库根目录的 `data/crawler-samples/codeforces/`，从其他工作目录执行脚本也使用此默认位置：

| 文件 | 内容 |
| --- | --- |
| `cf_raw.json` | API 原始响应，保留原始字节，含题目与统计数据 |
| `cf_sample.json` | 转换后的题目对象数组，供推荐组读取 |
| `cf_fields.json` | 完整题目列表中出现的字段、类型、出现次数与缺失次数，以及来源和报告生成时间 |

`data/` 已被 Git 忽略，运行会覆盖输出目录中同名的三个文件。脚本只导出本地文件，不访问平台数据库。

调整样本量或输出目录：

```powershell
python -X utf8 tools/crawlers/codeforces_sample.py --limit 100 --output-dir data/crawler-samples/cf-100
```

已保存原始响应后，可离线重新导出并统计字段：

```powershell
python -X utf8 tools/crawlers/codeforces_sample.py --input-json data/crawler-samples/codeforces/cf_raw.json --limit 10
```

接口请求或响应校验失败时，脚本返回非零状态；读取与转换失败不会覆盖已有输出。重新运行失败后仍存在的文件可能属于上一次成功采集，应核对报告时间。批量采集工具后续需要复用共享节流；CF 官方规定每两秒最多一次 API 请求，本工具每次运行只请求一次。

## Codeforces 样本字段

| 字段 | JSON 类型 | 来源与说明 |
| --- | --- | --- |
| `platform` | string | 固定为 `codeforces`，与 `problem_id` 联合识别题目 |
| `problem_id` | string | 拼接 `contestId` 与 `index`，例如 `2000A` |
| `contest_id` | integer | 原始 `contestId` |
| `problem_name` | string | 原始 `name` |
| `problem_rating` | integer / null | 原始 `rating`，缺失保留 `null` |
| `tags` | string[] | 原始标签；缺失时使用空数组，是否缺失可查原始 JSON |
| `problem_url` | string | 原站 contest / gym 题目链接 |
| `statement_html` | null | 此接口不含题面正文，预留供后续采集 |

缺少可定位 `contestId/index` 的条目及非编程题不进入转换样本；重复题号仅导出一条，原始响应和字段统计保留全部条目。若可用题目不足，样本数量会小于 `--limit`。原始可选字段以 `cf_fields.json` 的完整统计为准，不能只凭第一道题判断。

下一步与推荐组核对必需字段、缺失值和标签语义，再决定是否增加题面、比赛日期等字段。近年题目筛选需要通过比赛元数据的 `startTimeSeconds` 关联时间。AtCoder Problems 的估算难度应保留来源，不能直接当作 CF Rating 使用。

## AtCoder 元数据采集

AtCoder 元数据来自第三方 AtCoder Problems 项目的公开数据集，题目列表与估算难度分开下载，按题目 `id` 匹配。在仓库根目录运行：

```powershell
python -X utf8 tools/crawlers/atcoder_sample.py
```

脚本下载两个资源，请求之间等待 1.1 秒，符合维护者要求的超过一秒间隔。输出位于仓库根目录的 `data/crawler-samples/atcoder/`：

| 文件 | 内容 |
| --- | --- |
| `atcoder_raw.json` | 完整题目原始响应，保留原始字节 |
| `atcoder_models_raw.json` | 完整难度模型原始响应，保留原始字节 |
| `atcoder_problems.json` | 全量转换后的题目对象数组，包括缺少难度的题目 |
| `atcoder_sample.json` | 最多 20 道题的字段样本，优先选取有难度数据的题目 |
| `atcoder_fields.json` | 两种资源的字段类型、出现与缺失次数，以及匹配、难度覆盖、导出数量和来源 |

`--limit` 只影响独立样本，全量文件仍包含所有可定位题目。全量文件保留输入顺序，按题目 ID 去重，不按年份筛选。缺少有效 `id/contest_id` 的记录保留在原始响应中，但不进入转换文件。运行会覆盖输出目录中的上述同名文件；网络或读取、转换失败返回非零状态，并在导出前停止。输出位于被忽略的 `data/` 中。

转换字段沿用 `platform/problem_id/contest_id/problem_name/problem_rating/tags/problem_url/statement_html`，另保留以下信息：

| 字段 | 类型与说明 |
| --- | --- |
| `platform` | 固定为 `atcoder` |
| `problem_id` / `contest_id` | string，分别来自原始 `id/contest_id`，保留原站题号 |
| `problem_index` | string / null，原始比赛题序 |
| `problem_name` | 优先原始 `name`，没有时使用 `title` |
| `problem_rating` | integer / null，AtCoder Problems 显示难度，与现有 API 采集逻辑保持同一转换口径 |
| `difficulty_raw` | number / null，原始模型难度，可为负数；不能直接当成显示难度 |
| `difficulty_source` | 有有效难度时为 `atcoder_problems`，否则为 null；这是模型估算，并非 AtCoder 官方难度 |
| `difficulty_is_experimental` | boolean / null，保留模型的实验状态 |
| `tags` / `statement_html` | 此数据源不含算法标签与题面，分别使用空数组与 null；不代表已经完成分类或题面采集 |

低于 400 的原始难度转换为 `400 × exp(raw / 400 − 1)`，之后四舍五入并取非负整数；其他有效难度直接四舍五入。缺少模型、difficulty 缺失或不是有效有限数时，难度保留为 null，原始值仍可在模型文件中核对。CF 和 AtCoder 难度保留平台语义，当前没有跨平台统一评分模型。

调整样本数量：

```powershell
python -X utf8 tools/crawlers/atcoder_sample.py --limit 100
```

已保存原始数据后，提供两个文件即可离线重新导出：

```powershell
python -X utf8 tools/crawlers/atcoder_sample.py --input-json data/crawler-samples/atcoder/atcoder_raw.json --input-models data/crawler-samples/atcoder/atcoder_models_raw.json --limit 10
```

## AtCoder 题面、样例与 SQLite

先运行上面的 `atcoder_sample.py` 生成 `atcoder_problems.json`，再采集原站题目页面并入库：

```powershell
python -X utf8 tools/crawlers/atcoder_collect.py --limit 20
```

脚本自动创建 SQLite 数据库和 `crawler_problems` 表。当前筛选范围内的所有元数据都会入库；`--limit` 仅限制本次尝试下载题面的数量。因此默认运行可能导入几千条元数据，但只为 20 道题填充题面与样例。每次请求结束后至少等待 1.5 秒，按顺序下载。

再次运行会跳过以相同语言参数成功采集的题目，并继续处理后面的题目。失败项会在下次运行时重试；使用 `--refresh` 可更新已有题面。主键为 `(platform, problem_id)`，重复运行不会新增同一道题的记录。更新元数据不会清除已保存的题面与样例；下载、解析或题面写入失败时保留上次成功的正文与样例，并记录错误。

指定题号、比赛或数据库文件：

```powershell
python -X utf8 tools/crawlers/atcoder_collect.py --problem-id abc370_a --problem-id abc370_b
python -X utf8 tools/crawlers/atcoder_collect.py --contest abc370 --all
python -X utf8 tools/crawlers/atcoder_collect.py --contest abc370 --all --refresh --database data/problem_bank.db
```

`--all` 与 `--limit` 不能同时使用。题号必须存在于元数据文件中；题号与比赛筛选同时提供时取交集。`--language en` 为默认值，只取英文部分；没有英文时回退到日文，避免把双语页面的样例重复保存。也可以指定 `--language ja`。转换保留题面中的公式标记与图片链接，并将相对链接转换为绝对链接。

### 样例直接保存在题目中

`statement_html` 是包含样例章节的完整题面 HTML，`samples` 是同一条题目记录里的 JSON 数组（SQLite 中使用 TEXT 保存）。没有独立样例表。样例按编号配对，按 HTML 规则忽略紧接 `<pre>` 开始标签的一个排版换行，其余输入输出的空格、空行和结尾换行保留，换行统一使用 `\n`。示例：

```json
{
  "platform": "atcoder",
  "problem_id": "abc370_a",
  "samples": [
    {"index": 1, "input": "1 0\n", "output": "Yes\n"},
    {"index": 2, "input": "1 1\n", "output": "Invalid\n"}
  ]
}
```

这里的样例是题面公开的示例输入输出，并非评测用的完整测试数据。没有样例的题目可保存空数组；如果已有样例而新页面未解析到样例，刷新会失败并保留旧数据。无法确定配对关系或缺少样例内容时仍会报错。

AtCoder 特殊格式的处理如下：

- 只有输入章节明确说明无输入时，允许仅输出样例，并将 `input` 保存为 `""`；不凭缺少输入样例推断无输入。
- 原站明确声明巨大输出不予刊载时，保留输入，将 `output` 保存为 `null`，另用 `output_note` 保存官方说明。网页显示“输出说明”，不提供复制输出按钮；该说明不是可用于判题的期望输出。
- APG4b / APG4bPython 的练习优先读取正式样例，描述中较低层级的重复演示和“回答例 / 解答例”里的程序输出保留在正文。普通课程含多个独立例题，保存完整正文，`samples=[]`，不混成一道题的判题样例。
- 对历史题的输出编号笔误，仅在样例输入编号从 1 连续递增、输入与输出章节紧邻且交替出现、输出编号重复时，按相邻章节恢复配对。不会覆盖任何一个输出；其他重复或歧义仍失败。
- 原站 HTTP 404 或空题面继续记为失败，并显示原站未公开、已移除或系统测试占位的提示，不以空内容标记成功。重跑同步会重试这些记录，默认跳过已成功采集的题目。

主要数据库字段如下，本地与服务端共用的完整建表语句见 `feat/api/acm_api/problem_bank.sql`：

| 字段 | 内容 |
| --- | --- |
| `platform` / `problem_id` | 联合主键 |
| `contest_id` / `problem_index` / `problem_name` / `problem_rating` | 比赛、题序、题名与估算难度 |
| `problem_url` / `tags` / `metadata_json` | 原站链接、标签 JSON、完整元数据 JSON |
| `statement_html` / `statement_text` | 完整题面 HTML 与便于检索的纯文本，均含样例章节；纯文本会整理排版空白 |
| `statement_language` / `requested_language` | 实际保存的语言与本次请求的优先语言 |
| `samples` / `sample_count` | 同一题目中的样例 JSON 数组与组数 |
| `statement_source_url` / `statement_sha256` / `statement_fetched_at` | 题面来源、原始页面 SHA-256 与成功采集时间（UTC） |
| `last_fetch_status` / `last_attempt_at` / `last_error` | 最近尝试的状态（never / ok / failed）、时间与错误 |

查询某道题：

```sql
SELECT problem_name, statement_html, samples, sample_count
FROM crawler_problems
WHERE platform = 'atcoder' AND problem_id = 'abc370_a';
```

Python 读取时用 `json.loads()` 还原样例数组：

```python
import json
import sqlite3
from contextlib import closing

with closing(sqlite3.connect("data/problem_bank.db")) as db:
    db.row_factory = sqlite3.Row
    row = db.execute(
        "SELECT * FROM crawler_problems WHERE platform=? AND problem_id=?",
        ("atcoder", "abc370_a"),
    ).fetchone()
    problem = dict(row) if row else None
    if problem:
        problem["samples"] = json.loads(problem["samples"])
```

### 缓存与采集报告

默认内容输出位于 `data/crawler-samples/atcoder/`：

| 文件 | 内容 |
| --- | --- |
| `html/题号.html` | 成功解析的原始页面缓存 |
| `atcoder_content.json` | 本批次成功采集的题目对象，包含完整题面、样例与来源信息 |
| `atcoder_content_report.json` | 本批次成功、失败、跳过数量、错误清单，以及数据库累计元数据、题面和样例数量 |

JSON 和报告每次覆盖，数据库累计保留。没有待采集题目时，本批次 JSON 为 `[]`，已有数据库内容仍保留。某道题失败不会阻止后续题目；存在失败时退出状态为 1，中断时为 130，全部成功或全部跳过时为 0。可用已保存 HTML 离线解析、刷新数据库：

```powershell
python -X utf8 tools/crawlers/atcoder_collect.py --problem-id abc370_a --refresh --html-dir data/crawler-samples/atcoder/html
```

`--metadata-json` 可指定其他元数据文件，`--output-dir` 可指定缓存和报告目录。`data/` 已被 Git 忽略，数据库和页面缓存不会提交到仓库。题面 HTML 是原站内容；站内详情页使用 DOMPurify 清理 HTML，并用本地 KaTeX 渲染公式。

## 服务端初始化与管理员采集

部署到服务器的 `feat/api/` 包含共用题面解析器和题目表结构。安装 API 依赖后，可以在 `feat/` 目录初始化服务端数据库：

```powershell
python -m api.init_db --database ./data/acm_forever.db
```

也可省略 `--database`，使用 `ACM_DATABASE_PATH`。初始化可重复运行，不清空已有数据，服务启动时同样自动建表。该命令只负责表结构与默认设置，Web root 账号仍按 API 服务既有的启动配置创建。

管理员使用 `POST /api/admin/problems/sync` 触发服务器直接读取公开比赛题目列表和题面，无需先运行本地脚本或上传 JSON。支持 `platform=atcoder/codeforces`，CF 当前支持普通公开比赛。接口返回任务 ID，进度通过 `GET /api/tasks` 查询，也可用既有任务取消接口停止。完整参数、鉴权与请求示例见 [API 调用指南](api.md#管理员采集新题目)。

网页入口是 **管理后台 → 题库管理**。顶部可 **初始化数据库**（补齐表结构，保留已有数据）；**拉取范围 → 该平台全部题目** 调用 `scope=platform`，先导入 AtCoder Problems / CF 官方 problemset 公开目录，再以 `batch_size` 自动处理所有待采题面与样例。默认跳过成功题目，失败记录持久化，取消或重启后再次运行可继续处理。全平台模式不传比赛 ID、指定题号或总数量上限；批次大小为 1–100。具体范围及任务进度字段见 API 调用指南。

成功题目保存到服务端 `crawler_problems` 表，并在同一事务内更新 `recommendations` 目录，因此管理中心与成员题库列表可以读取题名。样例仍位于题目自己的 `samples` 字段，题面 HTML 保留样例章节；题库网页的“打开题目”进入站内详情页，读取数据库中的正文与样例，尚未采集正文时显示等待提示。AtCoder 从官方列表获取题名，不获取第三方难度模型，新题难度为 null；CF 保存 API 题目列表提供的 Rating 与标签，题号统一为 `cf_比赛ID题序`。已有难度和标签不会因缺少这些数据而被清空。

## 验证

以下测试使用合成 JSON、HTML 与临时 SQLite 数据库，覆盖字段转换、语言选择、样例空白保留、重复入库、断点续采、失败时保留旧数据和事务回滚，不请求外网：

```powershell
python -X utf8 -m unittest discover -s tools/crawlers/tests -p "test_*.py"
```

## 数据来源

- [Codeforces API 说明（认证、响应与频率限制）](https://codeforces.com/apiHelp)
- [Codeforces API 方法（problemset.problems、contest.list）](https://codeforces.com/apiHelp/methods)
- [Codeforces Problem 字段说明（题目元数据）](https://codeforces.com/apiHelp/objects#Problem)
- [AtCoder Problems API 文档（第三方数据与估算难度）](https://github.com/kenkoooo/AtCoderProblems/blob/master/doc/api.md)
