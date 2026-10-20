# V0.3 API 标签标注工具

本工具独立于论坛与数据库，复用 `label_pipeline.py` 的 prepare、merge_one 和 evaluate。
不改动现有词表、映射、提示词及原始数据。当前交付仅经过离线/Mock 测试，未验证真实模型访问权限、计费和标注质量。

## 新增文件清单

全部位于原测试包目录，共 23 个源码/配置/文档文件：

```text
annotate_api.py
evaluate_api.py
annotation_api/
  __init__.py
  config.py
  adapter.py
  prompt.py
  schema.py
  client.py
  storage.py
  runner.py
  evaluation.py
tests/
  api_helpers.py
  test_adapter.py
  test_schema_api.py
  test_api_client.py
  test_runner.py
  test_evaluation_api.py
  run_mock_smoke.py
requirements-api.txt
requirements-api-lock.txt
.env.example
.gitignore
README_API.md
```

另创建被忽略的 .venv、cache、outputs 和 Python 字节码缓存。
本次没有修改已有文件。原有 17 个文件 SHA-256 检查一致，Git 分支为 feat/forum-dev，未提交或推送。

本次离线验收：85 个单元测试通过（原有 14 + 新增 71），pip check 无依赖冲突。
额外完成 SDK MockTransport 双题演示和实际探索集 ATC 10 题 dry-run，真实 API 调用均为 0。

## 环境

本机已验证 Python 3.14.3。四项直接依赖：openai 2.54.0、python-dotenv 1.2.4、jsonschema 4.26.0、httpx 0.28.1。
`requirements-api.txt` 固定直接依赖，`requirements-api-lock.txt` 记录本次环境的完整依赖版本。

PowerShell：

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api-lock.txt
.\.venv\Scripts\python.exe -m pip check
```

已有 `.venv` 时无需重新创建。无需激活虚拟环境，避免 PowerShell 执行策略影响。
CMD 使用 `cd /d "D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3"`，后续命令相同。

## 离线测试与预览

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe annotate_api.py --provider openai --platform atcoder --input data/exploration_inputs_20.jsonl --limit 10 --dry-run
```

默认也是 dry-run。此路径不加载 `.env` 或 API Key，不创建 SDK 客户端，不写标注产物或请求缓存，不生成 AI 预测。
逐题显示身份、题面哈希及预处理状态；最终显示 selected_count、ready_for_ai、api_calls、files_written。
现有探索集筛选结果为 10 道 AtCoder，API 调用次数为 0。本阶段没有处理留出集。

生成可查看的虚构题目 Mock 示例：

```powershell
.\.venv\Scripts\python.exe tests/run_mock_smoke.py
```

示例只使用 HTTPX MockTransport 和无效的测试凭据。产物在 `outputs/mock_smoke/runs/<指纹前缀>/`，
`outputs/mock_smoke/MOCK_ONLY.json` 明确说明：这些不是实际探索题预测，Token 为模拟数值，真实 API 调用为 0。
示例 summary 中的 api_calls 统计 Mock 客户端调用，不代表付费调用。

## 配置与后续单题调用

以下真实调用步骤仅供下一阶段批准后使用，本次开发未执行。

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

在本地编辑器填写 `.env`，不要通过日志、聊天或命令行展示密钥：

```dotenv
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=
ANNOTATION_RESPONSE_FORMAT=json_schema
ANNOTATION_TOKEN_PARAMETER=max_completion_tokens
```

`OPENAI_MODEL` 可填写经确认的 `gpt-5.4-mini` 或其他已核实能力的模型，生产代码没有固定模型。
进程环境变量覆盖 .env；`--model` 覆盖模型配置。只有 `--execute` 才读取密钥并允许请求。

确认模型支持 Chat Completions、json_schema 和所选 Token 参数后，先执行一题：

```powershell
.\.venv\Scripts\python.exe annotate_api.py --provider openai --platform atcoder --input data/exploration_inputs_20.jsonl --limit 1 --resume --max-retries 0 --max-output-tokens 4000 --execute
```

Token 上限需要结合模型调整，它可能包含推理 Token；过小可能截断输出，已经消耗的 Token 仍可能计费。
首题成功并审核后，保持相同模型和参数执行 10 题：

```powershell
.\.venv\Scripts\python.exe annotate_api.py --provider openai --platform atcoder --input data/exploration_inputs_20.jsonl --limit 10 --resume --max-retries 0 --max-output-tokens 4000 --execute
```

首题缓存成功时只新增剩余 9 题请求。上述两条命令本次没有运行。

## CLI

| 参数 | 含义 |
|---|---|
| --provider | openai（默认）或显式选择 compatible |
| --model | 覆盖 OPENAI_MODEL |
| --platform | all、codeforces、atcoder |
| --input | UTF-8 JSONL 路径，允许 UTF-8 BOM |
| --output | 独立输出目录，不是 JSONL 文件名；包内必须在 outputs 下 |
| --limit | 平台筛选后、按输入顺序选取的唯一题目数，不是新增 API 请求数 |
| --dry-run | 预览，不读密钥、不写文件、不请求 API |
| --execute | 显式允许网络请求；与 --dry-run 互斥 |
| --resume | 恢复已有输出；已有目录缺少该参数时禁止覆盖 |
| --reviews | 独立人工审核 JSONL；人工确认结果优先 |
| --max-retries | 单题限流后的额外重试次数，默认 2；首次建议 0 |
| --timeout | 请求超时秒数，默认 60 |
| --request-interval | 请求间隔秒数，默认 1 |
| --max-output-tokens | 可选输出 Token 上限，无默认上限 |
| --retry-failed | 显式重新请求已知失败；不能重发 unknown_delivery |

首次只推荐 AtCoder 探索集。程序不会自行搜索或处理其他数据文件。

## 输入、预处理与标注规则

支持探索集扁平字段：problem_key、platform、title、url、raw_tags、statement_markdown、statement_status、
editorial_status、verified_editorial_markdown、content_hash。
也兼容带 contest_id/problem_id、tags.values 和 statement.markdown 的原始记录；
CF 原始 editorial.status=ok 的题解遵循现有 make_samples 的已匹配约定。
上游必须保证该状态确实表示可靠匹配；工具不会联网核验题解。

身份由 `platform:contest_id:problem_id` 确定，和原始身份字段、可识别官方 URL 交叉检查。
不一致记录错误；不会用标题或行号生成身份。
补齐字段后调用 prepare，不重复实现 CF 字典映射。

内部数据包含 rule_base（prepare 的完整结果）、evidence（题面及可靠题解）、source_line 和 annotation_input_hash。
缺失 content_hash 时根据身份、标题和题面派生 SHA-256；已有 hash 原样保留。
始终根据实际题面、标签和可用证据生成 annotation_input_hash，防止上游忘记更新 hash。

空标签合法；缺少有效题面时不调用 API，保存规则基线和 missing_statement 错误。
同 ID、相同标注输入去重；同 ID 内容或人工状态冲突时阻止该 ID 的请求。
无效 JSON 或字段作为逐行错误，不阻塞其他正常题。

CF 精确标签由 merge_one 保留；仅明确的 resolved_cf_hints 可以去掉对应临时标签。
AtCoder 优先具体标签，也允许临时标签或空数组。一种有依据的主解法用于标注，
其他已验证解法可以记录在 reason 中。每个 AI 结果都是 pending_review，不使用自报置信度当正确率。

复用现有中文提示词，在系统消息补充数组形式的 API 传输约定。
用户消息是 JSON 编码的外部数据，题面及题解中的指令没有指令权限。

## 结构化输出与兼容性

官方 SDK：Chat Completions，stream=false，SDK max_retries=0。
默认 json_schema、strict=true、对象 additionalProperties=false、所有字段 required。
100 个具体 ID 和 15 个临时 ID 直接从 V0.3 词表生成 enum。

API 字段：problem_key、content_hash、specific_tag_ids、provisional_tag_ids、resolved_cf_hints、evidence_kind、reason。
resolved_cf_hints 的传输形式为数组，例如：

```json
[{"hint":"data structures","specific_tag_ids":["segment_tree"]}]
```

本地校验后转成原合并函数要求的字典。检查额外字段、重复 JSON 属性、身份/hash、标签种类、
重复或空线索解析、非空理由以及证据来源。拒答、截断和空内容不当成成功。
中文标签通过词表查出，不由模型编造。

模型参数能力由配置显式声明：默认 max_completion_tokens；只有确实支持旧参数的接口才配置 max_tokens。
只有确认不能使用 Structured Outputs 的兼容接口才显式选择 json_object；仍执行同样本地校验。
不发送 temperature、reasoning 等未配置参数，不探测能力，不静默降级，不切换模型。
官方 provider 仅接受 https://api.openai.com/v1；其他 HTTPS 地址必须显式选择 compatible 并使用对应服务的凭据。
base_url 禁止嵌入认证信息、查询参数或 fragment。

参考：[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)、
[Chat Completions](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)、
[错误类型](https://developers.openai.com/api/docs/guides/error-codes)。

## 文件与恢复

默认输出目录：`outputs/<模型标识>/<完整运行指纹>/`。
运行清单包含服务商、模型、请求参数、平台筛选、输入文件 SHA-256、词表/映射/实现哈希、提示词及 Schema 哈希。
limit 不属于运行指纹，因此 1 题→10 题可以恢复；减少 limit 也不会删除原清单中的题目。
每题指纹另外包含题目身份、题面版本和实际消息。换模型、数据、提示词、代码或主要请求参数会产生新运行空间。

| 文件 | 内容 |
|---|---|
| predictions.jsonl | 不可变模型建议/规则结果，用于评估，绝不写人工修正 |
| merged_results.jsonl | CF 规则与 AI 建议合并后的结果，人工审核覆盖优先 |
| errors.jsonl | 已知失败、未知请求状态和输入错误；保留历史错误 |
| summary.json | 本次恢复运行计数、选中题目累计已知 Token、未知用量与停止原因 |
| manifest.json | 冻结数据集身份、题面/证据哈希及运行配置 |

predictions 的 specific_tag_ids 是 AI 新增 ID，resolved_cf_hints 是规范化字典；
evaluation_specific_tag_ids 是保留 CF 精确标签后的规则+模型集合。
对应中文字段逐一匹配各自 ID。评估会重新构造该集合并检查一致性。
记录 requested_model 与 API 实际返回 model、判定理由、taxonomy_version、annotation_rule_version、prompt_version、
review_status、human_review_status、api_call_status、usage、error、updated_at。
usage 缺失时为 null，不伪造零用量。

每题追加输出并 flush/fsync；缓存和摘要使用原子替换。
响应先进入缓存，再校验和合并，因此本地写入中断后可以免费重放。
单写入者锁避免同一输出目录的并行重复请求；进程退出后系统释放锁，无需删除 .writer.lock。
Windows 缓存使用单层完整哈希命名空间，避免多层哈希导致路径过长。
末尾未完成 JSONL 行可以恢复；中间损坏行会报错，不能静默跳过。

只有明确限流会在本次批次中按上限退避重试；quota/auth/configuration 错误停止批次。
网络超时、连接异常、5xx 或发送后中断标记 unknown_delivery，默认不重发，其他题可以继续。
拒答、截断、无效输出不自动追加付费修复请求。
--resume 复用成功结果，并保留失败结果。修复已知问题后，--retry-failed 可显式重试已知失败，
保留历史 Token 用量；该选项仍不能重发未知请求。

本地不能保证付费请求严格只执行一次：服务端可能已处理但响应未保存。
unknown_delivery 的费用需要人工核对供应商记录。新输出目录/配置/模型属于新的运行，可能重新收费；
不要删除缓存或另建目录来绕过未知状态。不同输出目录不会共用缓存，以免没有共同锁时重复发送。
缓存文件损坏、磁盘故障或系统断电的硬件行为也无法被应用完全保证。

## 人工审核与评估

独立审核记录格式：

```json
{"problem_key":"atcoder:demo001:demo001_1","reviewed":true,"taxonomy_version":"0.3-draft","content_hash":"复制实际题面哈希","accepted_specific_tag_ids":["prefix_sum"],"accepted_provisional_tag_ids":[],"reviewer":"人工审核者"}
```

示例身份是虚构的。对真实题目应按实际证据审核，不能直接复制 AI 标签当答案。
通过 --reviews 指定审核文件，每次新模型运行也应传入同一权威审核文件。
human_confirmed / human_review_status=approved / reviewed=true 都受到保护；审核版本及标签必须合法。
缺少明确标签的“人工确认”记录会报错，不会按空标签处理。
题面 hash 变化时保留人工标签并标记 human_review_stale，不自动覆盖；缺少审核 hash 时标记版本未核实。
同一输出目录内已保存的人工结果即使后续不传 --reviews 也不会被替换。
人工修改应通过独立审核文件导入，不要编辑 predictions.jsonl。

```powershell
.\.venv\Scripts\python.exe evaluate_api.py --predictions '<实际运行目录>\predictions.jsonl' --gold '<人工审核文件>' --output outputs/evaluation.json
```

程序自动寻找同目录 manifest.json 和 errors.jsonl，也可用 --manifest、--errors 指定。
包内评估报告只能写入 outputs，不能覆盖输入或现有测试包源文件。
仅 JSON 布尔值 reviewed=true 参与评估；字符串 "true"、数字 1 均拒绝。
检查重复身份、标签版本、题面和证据哈希、预测来源、混合运行配置。
旧人工模板没有 hash 时要求冻结 manifest 关联，并在报告注明；今后人工审核应补 hash。

质量指标复用 evaluate：micro Precision、Recall、F1、完全匹配率。
统计的是未经人工修改的规则+模型具体标签集合，CF 精确映射参与该集合。
另外报告全部选中题目的具体标签覆盖率、含临时标签题目比例、待审核比例、预测覆盖率、当前失败率。
历史错误后成功的题目不再计作当前失败。缺失预测仍留在分母中，作为漏标处理，不能算完全匹配。
没有已审核答案时质量指标为 null，并明确提示无法计算准确率。

比较模型时必须核对相同 dataset_sha256、标签版本、人工答案与失败口径。
多解题的人工答案需遵循同样主解法标注约定；标签集合不同不必然说明某种解法错误。
合法 ID 与结构合规不能证明算法判断正确；词表目前没有完整算法父子/线索白名单，语义冲突仍需要人工判断。

## 费用与安全边界

当前真实 API 请求次数为 0、费用为 0。安装依赖仅访问包索引。
下一阶段先 limit=1、max-retries=0，结合输出上限控制单题消耗，查看 usage 后再扩大到 10 题。
实际费用取决于所选模型当时的输入、输出及缓存计价，不在程序里硬编码价格。
未提供 Token 上限时没有应用层输出预算限制；Token 上限不等于金额硬上限。
建议同时设置供应商账户支出限制。

.gitignore 忽略 .env/.env.*（保留 .env.example）、.venv、cache、outputs、__pycache__ 和字节码。
运行清单与日志不保存密钥或认证头；错误不打印 SDK 原始载荷；已知密钥从响应字段中脱敏。
不要启用 SDK/HTTPX 的外部调试日志，不要手工把真实密钥放进输入数据或其他文件。
本工具不连接论坛数据库，不提交或推送 Git。
