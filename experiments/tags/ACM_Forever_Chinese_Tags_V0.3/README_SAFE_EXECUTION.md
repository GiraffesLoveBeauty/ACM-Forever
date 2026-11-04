# 7G：安全执行器与防重复计费

本阶段只运行离线测试、Mock 和 dry-run。未读取真实凭据，未发起真实 AI 请求。
新的持久记录放在当前数据根的 `execution/`；原 10 题、人工历史、缓存和备份保持原样。

## 真实调用的保护路径

`annotate_api.py` / `translate_api.py` 执行模式 → `execute_processing.py` →
`execute_batch` 校验完整绑定计划 → `Executor` → 题目/任务类型 OS 锁 → 最新持久状态检查 →
写入 dispatched → 一次性许可 → APIClient 检查 → HTTP 发送前再次检查 → 保存响应 → 校验/发布 → completed。

- 默认 dry-run 不加载 `.env`，不创建任务锁或持久目录，不发送请求。
- 真实执行必须显式 `--execute`，并提供 `--plan`。缺少计划时在加载凭据前拒绝。
- 计划绑定任务类型、Provider、端点、模型、输出模式、Token 参数和上限；核验计划摘要、当前目录代次及完整规划结果。
- 过期或参数不一致的计划直接拒绝；请重新生成，不要编辑旧文件的摘要以绕过检查。
- 每题在锁内重新读取人工修改、持久标签、译文索引、历史请求、任务策略及正文绑定。
  在客户端层和 HTTP 请求钩子再次检查，避免仅依赖旧计划。正文/人工记录在发送前变化会阻断请求。
- 单次许可严格限制一个配置一致的 POST、完整请求体及固定 `/chat/completions` 地址。
  SDK 自动重试和真实执行的应用重试均为 0；禁用自动重定向及环境代理，不自动换模型/输出模式。
- 旧循环仅保留显式注入离线 Fake/MockTransport 的测试用途；真实 APIClient 调用及直接 SDK 调用没有许可均会被拒绝。
  这防止工程入口误用，并不把任意恶意 Python 代码变成安全沙箱。
- 每批显示任务类型、选择题数及规划的 AI 数量；每题独立保存，某题失败不覆盖其他已完成结果。

## 稳定身份与兼容性

任务 ID = 题目身份、标签/翻译任务类型、规范输入语义摘要、提示词版本/内容摘要、Schema 摘要、
标签词表/映射规则或翻译目标语言、Provider/端点/模型及输出参数、live/mock 模式的规范 JSON SHA-256。

运行位置、输出绝对路径、无关源码、超时、请求间隔和重试数不改变任务 ID。
标签和翻译分别计算；翻译提示词变化不会改变标签任务身份。
输入/策略/模型参数改变不能直接当作缺失结果重发；不匹配或无法证明等价的旧结果阻断并要求核验。
旧 10 题通过原清单中的词表/映射/提示词/Schema、输入摘要及请求参数证据核验，无需迁移或删除旧缓存。
人工确认标签优先；已有增删、删除墓碑及完整确认记录保留在原 journal，自动执行不能覆盖。

## 持久状态与崩溃恢复

```text
<data-root>/execution/
  tasks/<task_id>.json          # 输入/策略/模型摘要、attempt_id、状态及每次尝试的事件链
  responses/<attempt_id>.json   # 脱敏后的响应及模型、用量、耗时、请求 ID
  results/<task_id>.json        # 不可覆盖的原始预测和已校验结果
  locks/<scope>.jsonl.lock      # 题目 + 任务类型的跨进程 OS 锁
```

JSON 使用既有 UTF-8、fsync、临时文件替换写入；响应/结果已存在时禁止不同内容覆盖。
锁复用 `Journal` 的 Windows `msvcrt.locking` / POSIX `flock`，持有整个请求和发布过程。
另一个进程不能领取同题同类任务；进程退出 OS 释放锁，但**时间过期不代表远程未处理**。

| 状态 | 后续行为 |
| --- | --- |
| pending | 可领取（首版创建后直接写 claimed） |
| claimed | 仍持锁则阻断；取得已退出进程的锁后转 failed_before_dispatch |
| failed_before_dispatch | 可安全重新领取，新 attempt_id，保留旧事件 |
| dispatched | 已持久写入发送意图；崩溃且无保存响应则转 uncertain |
| uncertain | 禁止重发；即使超时数天也不会自动解锁计费 |
| blocked | 配置、校验、响应或历史异常，禁止自动重试 |
| completed | 校验完整性并优先复用持久结果；缺失或冲突转人工核验 |

响应先落盘，再解析和激活。若进程在响应落盘后退出，相同策略可直接从响应完成本地恢复，不再次调用 API。
输入或模型参数改变时不激活旧响应。模型返回无效标签、截断或无法解析时，保留用量和响应摘要并阻断重发。
请求发送意图先写入会保守地阻断“刚写 dispatched、实际尚未发出”时的崩溃场景。

`uncertain` 处理：保留全部文件，查中转站请求记录/账单和本地 request_id/时间；完整响应存在时优先本地恢复。
无响应时需要人工明确认定结果及是否接受再次计费。本版不提供清空 uncertain、超时抢锁或强制重试开关。
既有备份工具已纳入白名单审查后的 execution 记录、结果与事件，隔离恢复后 unknown 状态仍然阻断。
响应可能包含题面/译文，按私有持久数据管理，不能提交 Git。

## PowerShell 离线演示

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'

# 真实 10 题只读检查：标注任务应为 0，不加载凭据。
.\.venv\Scripts\python.exe -B -X utf8 execute_processing.py --task annotation --platform atcoder --input data/exploration_inputs_20.jsonl --limit 10 --dry-run

# 可共享合成样本；独立目录位于仓库已忽略 data/ 下。禁止指向 data/labels。
$mockRoot = Join-Path 'D:\ACM Project\ACM-Forever\data' ('acceptance_7g_mock_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
.\.venv\Scripts\python.exe -B -X utf8 execute_processing.py --task annotation --platform atcoder --input tests/fixtures/crawler_records.json --limit 1 --mock --data-root $mockRoot
# 同一个命令再次执行：复用 Mock 结果，api_calls=0。
.\.venv\Scripts\python.exe -B -X utf8 execute_processing.py --task annotation --platform atcoder --input tests/fixtures/crawler_records.json --limit 1 --mock --data-root $mockRoot
.\.venv\Scripts\python.exe -B -X utf8 execute_processing.py --task translation --platform atcoder --input tests/fixtures/crawler_records.json --limit 1 --mock --data-root $mockRoot
.\.venv\Scripts\python.exe -B -X utf8 execute_processing.py --task translation --platform atcoder --input tests/fixtures/crawler_records.json --limit 1 --mock --data-root $mockRoot

# 生成页面并执行阻断网络的全量回归。
.\.venv\Scripts\python.exe -B -X utf8 demo_acceptance.py --run-tests
```

Mock 必须使用显式隔离根；同一根禁止混合 live 与 Mock 执行记录。
Mock 译文不激活真实翻译索引，重复时通过 Mock 任务结果复用；不能把 Mock 当作正式译文。

## 下一阶段真实单题翻译准备

先确认一题可用英文/日文正文、公式样例完整性及使用权限；只生成该题规范输入文件。
核对中转站文档/既有授权确认的实际模型 ID、端点、输出模式与 Token 参数，费用以中转站账单为准。
用 `plan_processing.py --input <single.json> --limit 1 --task-type translation --provider compatible --model <confirmed-model> --base-url <confirmed-url> --response-format <confirmed-mode> --token-parameter <confirmed-parameter> --max-output-tokens <confirmed-limit> --write --output outputs/plans/<new-name>.json` 生成绑定计划。
该命令不加载密钥、不发请求；输出文件必须新建。真实执行前再做同输入的 dry-run，确认只有一个翻译任务、标注 0，且无未解决历史请求。
后续获得真实调用授权才可指定 `--execute --plan <new-plan> --limit 1 --max-retries 0`，先核对 `.env` 与环境覆盖但不输出密钥。

上游尚无已验证的服务端幂等保证。本地状态、锁和不自动重试可抑制正常重复执行，
但不能绝对保证远程恰好计费一次；网络断连、主机掉电、人工强制迁移或独立旧客户端仍有风险。
不要在同一物理数据根之外复制任务后并发执行，也不要把本地 OS 文件锁当成跨主机分布式锁。
本阶段未测试中转站兼容性、价格、真实翻译质量或服务端幂等键。
