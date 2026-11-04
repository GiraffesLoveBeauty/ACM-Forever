# 阶段 7B：独立题目二次处理

本模块读取已爬取数据，持久保存算法标签与译文，叠加人工标签修改并导出元数据。
不采集 OJ 数据、不提交或判题，不管理 OJ 账号，不访问论坛数据库，不生成难度或推荐算法。
V0.3 词表、CF 映射、原始预测与原始爬虫文件保持不变。

## 已检查的数据

- `D:\ACM Project\DATA\contextpy_data_handoff_20261009\data\codeforces.json`、`atcoder.json`：各 200 题，外层 `problems`，题面有嵌套 Markdown/HTML、状态、语言、标签 values 和来源信息。
- `D:\ACM Project\DATA\cf_sample.json`：20 题数组，旧字段 problem_name/problem_url、整场前缀题号和 statement_html。
- 本阶段只检查这些格式，验收导入只使用已有探索集中的 10 道 ATC 成功结果，不处理留出集，也不全量导入上述文件。
- 新版格式和旧别名由本模块适配。HTML-only 保留 HTML，标记 html_only/needs_review，不进行可能丢失公式或图片的自动 HTML 转换。
- 没发现牛客真实交接文件；已实现稳定全局题号/比赛内题号的基础适配，但别名关联和标签映射需真实样本确认。

## 本地持久目录

默认 `D:\ACM Project\ACM-Forever\data\labels`，原根 .gitignore 的 `/data/` 已忽略。
支持 `TAG_DATA_ROOT` 或 CLI `--data-root`；相对覆盖路径以项目根为基准，仓库内只能放在 data/ 下，也可放在仓库外。
禁止将持久根置于 cache/outputs。初始项目根下没有 data/labels 同名业务目录。

```text
data/labels/
  annotations/<批次哈希>.jsonl      原自动标注完整记录，不可覆盖
  translations/
    requests/<翻译指纹>.json        独立请求状态与安全响应
    history/<翻译指纹>.json         译文或异常记录
    current.json                   激活可解析的真实结果；当前默认不做译文内容一致性校验
  catalog/
    generations/<版本哈希>/
      problems.jsonl               原题名、题面、链接及派生元数据
      auto_tags.jsonl              当前自动标签；不是人工有效标签
      manifest.json                版本与数量
    current.json                   原子版本指针
    writer.jsonl.lock              导入写锁
  manual/overrides.jsonl            永久人工事件，首次人工操作时创建
  exports/<有效结果哈希>.jsonl     可重新生成的最终元数据
```

导入先校验批次，再在写锁内读取当前版本，写完整新版本和 manifest，最后原子切换 current.json。
未提交完整的新目录不会成为当前版本；历史目录与自动标注原记录不删除。重复导入不新增相同历史。
同一 problem_key 的已明确来源链接会累计保留，不按标题推断跨 OJ 同题。
题面哈希或实际题面改变时建立新版本；检测到爬虫提供的哈希未随内容变化会拒绝导入。
缺少新版本自动标签时不会把旧题面 AI 标签直接作为当前结果；人工增删仍保留并提醒复核。

## 已有 10 题导入与查询

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'
$secondaryPython = '.\.venv\Scripts\python.exe'

# 纯离线，重复执行幂等
& $secondaryPython -B -X utf8 import_tags.py `
  --input data/exploration_inputs_20.jsonl --platform atcoder --limit 10 `
  --annotations outputs/gpt-6-luna/a1b33bb8bad67af96c193baf451ac483eaedb0c76d3fd7ae381709091ed4ccb5/merged_results.jsonl

& $secondaryPython -B -X utf8 manage_tags.py show 'atcoder:abc475:abc475_d'
& $secondaryPython -B -X utf8 export_tags.py

# 如需改变存储位置，应先复制完整持久目录，再指定配置；不是重新付费标注
# $env:TAG_DATA_ROOT = 'D:\ACM Project\ACM-Forever\data\labels'
```

默认 settings.json 使用 `{schema_version:1, storage:"persistent"}`；旧 auto_file 配置及显式文件接口继续兼容。
原人工历史可用 import_tags.py 的 `--migrate-manual` 指定；会验证历史链并复制，目标已有不同历史时拒绝覆盖。
本阶段旧人工历史文件不存在，所以没有迁移或创建真实人工修改记录。

```python
from tag_management import get_effective_tags, get_effective_tags_many, iter_effective_tags
from problem_processing.repository import Repository

one = get_effective_tags("atcoder:abc475:abc475_d")
many = get_effective_tags_many(["atcoder:abc475:abc475_d", "atcoder:abc469:abc469_a"])
rows = iter_effective_tags(platform="atcoder", tag_ids=["enumeration"], status="auto")
metadata = Repository().metadata_many()
```

批量接口读取一次自动文件、一次人工历史，建立按题号及历史事件的字典索引；不逐题扫描整份 JSONL。
一次调用使用固定自动目录版本，返回具体/临时 ID、中文名称、逐标签来源、人工状态及推荐可用标记。
普通单题接口保留兼容；长期持有 TagManager 表示固定版本快照，欲读取新提交版本应新建管理器。
需要的标签筛选是包含全部给定 ID；状态筛选支持 auto/corrected/verified/needs_review。

## 翻译模块

默认只预览，不加载密钥、不创建 SDK、不写请求；--mock 使用无凭据本地客户端，明确标记 mock，不激活到真实译文索引。
--execute 是未来真实运行的显式选项，本阶段没有执行。模型与地址均沿用本地 .env，不硬编码模型或密钥。
SDK 及应用层均不重试；超时或传输未知会保存状态并停批，重复执行不会再发送同一指纹。
JSON Schema 不兼容时记录异常，不静默切换 JSON Mode、模型或 Token 参数。

```powershell
# 实际探索题单题预览：选择完整英文版本，真实请求 0
& $secondaryPython -B -X utf8 translate_api.py `
  --input data/exploration_inputs_20.jsonl --platform atcoder --limit 1 --dry-run

# 英语、日语和中文的离线协议演示：Mock 调用，不是真实翻译
& $secondaryPython -B -X utf8 translate_api.py `
  --input tests/fixtures/translation_samples.jsonl --limit 3 `
  --mock --data-root data/labels_mock
```

语言判断使用文字特征和爬虫语言提示。简体中文为主时跳过；英文、日文和有实质外语的混合题面进入翻译。
检测到日文加完整英文题面时，优先完整英文版；缺少必要英文结构时标记 needs_review。
语言识别无法可靠覆盖所有语言和纯汉字日文，未知内容不强行送模型。

翻译前将代码块、行内代码、LaTeX、变量、图片和链接替换为不可修改的占位符。
输出协议为 title_zh + 带固定 id 的逐段 segments，校验段落数量/顺序、数字、占位符与 Markdown 标题/列表。
恢复后样例代码块内容原样保留；失败响应和用量保存，结果 needs_review，不激活为有效译文。
结构校验不能证明语义完全正确，也不能自动证明没有增加算法提示。真实翻译质量仍需后续授权实测和抽查。
部分含复杂 LaTeX 的整行会保守保护，可能留有原文，后续应细化表达式识别；本阶段不把 Mock 当成可发布译文。

缓存指纹包含翻译专属版本、提示词、Schema、原文/题名/内容哈希和模型请求参数；不共享标签缓存。
修改翻译提示词不会改变标签指纹。注意本阶段增加可选客户端 Schema 参数改变了旧标签客户端源文件哈希，
旧 annotate_api 的运行指纹可能改变；不要直接用旧 --execute 批次尝试恢复，先查询已持久化的可靠标签。
已有标签只缺译文时使用翻译入口；联合生成仅有 plan_tasks 的接口设计，不执行联合请求。
收到响应后本地中断的 received 状态不会自动重发；首版尚无专门的离线响应重放命令。

## 题目数据契约

输入兼容 JSON 数组、外层 problems 和 JSONL；标准元数据形状如下（示例为合成数据）：

```json
{
  "problem_key": "atcoder:offline:offline_en",
  "platform": "atcoder",
  "source_problem_id": "offline_en",
  "contest_id": "offline",
  "original_title": "Addition",
  "original_statement": "原始完整 Markdown",
  "translated_title": null,
  "translated_statement": null,
  "source_links": ["https://atcoder.jp/contests/offline/tasks/offline_en"],
  "raw_tags": [],
  "effective_tag_ids": ["enumeration"],
  "difficulty_raw": null,
  "content_hash": "来源/派生题面哈希",
  "verified_content_hash": "统一内容校验哈希",
  "metadata_version": "secondary-1",
  "translation_status": "missing",
  "review_status": "auto",
  "rights_status": "unknown",
  "translation_rights_status": "unknown",
  "display_requires_rights_check": true
}
```

爬虫负责来源 ID、题名、题面/HTML、链接、原标签、原始难度、采集时间和可用的语言信息。
二次处理负责规范身份、派生哈希、标签来源/覆盖、译文及其版本、有效标签和状态。
原始难度只保留，不做统一评级。来源和翻译授权状态默认 unknown，不能视为允许完整转载；展示前由团队按平台规则核查。

成功译文另存 problem_key、source_language、target_language、original_title/statement、source_links、title_zh、statement_zh、
translation_status、translation_model、translation_version、source_content_hash、source_verified_hash、usage、elapsed_seconds 等字段。
原题面和译文有明确区分；人工译文覆盖层预留，管理后台尚未实现。

## 验证、备份及后续

```powershell
& $secondaryPython -B -X utf8 -m unittest discover -s tests
& $secondaryPython -B -X utf8 tests/test_secondary_processing.py SecondaryTests.test_mock_1000_and_5000_cold_loading_and_batch_query
```

全部测试使用临时合成数据、HTTPX MockTransport 和无效测试凭据，真实网络传输在新测试中被阻断。
迁移核验和原文件哈希核验记录位于 data/labels/exports/migration_check.json；最终验收统计位于 stage7b_validation.json。
冷加载计时包含自动文件解析/标签适配；索引批量计时使用已冷加载字典，不含该次冷加载。数据为模拟题目，不代表生产并发性能。

持久数据不会随实验 outputs 清理，但 Git 忽略不等于备份。应停止相关写入后备份整个数据根目录，
尤其 manual、annotations、catalog 和未解决请求状态；目前没有自动备份/恢复命令。
下一步建议补充备份/恢复、真实牛客样本适配、HTML 转换、翻译响应离线重放及授权信息管理。
正式后端接入和数据库迁移必须另行确认，继续遵循当前 Quart + SQLite + aiosqlite 的统一服务边界。
