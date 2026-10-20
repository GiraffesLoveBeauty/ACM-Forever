# ACM-Forever 中文算法标签体系与测试集 V0.3

> Git 归档说明：以下目录表描述本机的原始 V0.3 数据包。完整 OJ 题面、题解、真实运行结果和留出集不随源码提交；参见 [README_ARCHIVE.md](README_ARCHIVE.md)。离线单元测试使用仓库内的模拟样本，不需要这些本地数据文件。

适用范围：当前用户提供的 Codeforces、AtCoder 爬虫 JSON。牛客待获取实际数据结构后扩展。

## 和 V0.2 最大的区别（用户已确认的 B 方案）

- 维持 **100 个具体中文算法标签**，如「线段树」「优先队列」「树状数组」「并查集」「贪心」。
- 新增 **15 个可临时展示的大类/算法家族标签**，如「数据结构·待细化」「动态规划·待细化」「最短路·待细化」。它们有独立稳定 ID：`pending_data_structures`、`pending_dp` 等。
- CF 原标签与具体算法精确对应时，直接映射；过宽泛时先保留对应临时标签。AI 真正识别出具体解法后，**只移除被明确解决的那一种临时标签**。未解决的不删除；其他 CF 官方标签仍保留原样。
- ATC 原标签为空：AI 无法确定细分算法、但对算法大类有依据时可选临时标签；完全不知道时**不强行给大类**。
- 前端展示区分两类标签：具体标签正常显示，临时标签统一附「·待细化」；推荐算法默认只使用具体标签（临时标签仅用于初期粗筛和人工审核）。
- CF `interactive` / `*special` / `communication` 为题目形式属性，不是算法标签。

## 真实数据与文件目录

用户上传的爬虫交接包包含 **200 道 CF + 200 道 ATC**，本包保留它们的**离线规则预处理产物**，不包含原始全文题库的复制。两种数据的真实原始字段是 `tags.values`、`statement.markdown`、`difficulty`、`editorial`、`content_hash`。

| 路径 | 内容 |
|---|---|
| `tag_taxonomy_v0.3.json` | 100 个具体标签 + 15 个临时大类（中文名、稳定 ID） |
| `cf_mapping_v0.3.json` | 33 种实际观察到的 CF 标签：15 直接映射、15 线索→临时、3 题目属性 |
| `label_pipeline.py` | 离线 Python：准备 / AI 结果合并 / 评估 |
| `make_samples.py` | 固定随机种子，从同一批爬取 JSON 抽探索集和独立保留集 |
| `ai_annotation_prompt_v0.3.md` | 可用于 Codex 后续编写的批量 AI 标注提示词 |
| `data/codeforces_baseline_all.jsonl` | 200 道 CF 规则预标注（不是人工真值） |
| `data/atcoder_baseline_all.jsonl` | 200 道 ATC 空标签/待 AI 状态（不是预测） |
| `data/exploration_inputs_20.jsonl` | **探索集**：CF 10 + ATC 10，含题面、标签和部分已匹配 CF 题解 |
| `data/holdout_inputs_60.jsonl` | **正式保留集**：CF 30 + ATC 30，含题面，暂不用于调参 |
| `data/exploration_rule_baseline_20.jsonl` | 探索集规则输出，可与 AI 预测对比 |
| `data/holdout_rule_baseline_60.jsonl` | 保留集规则输出，在冻结规则后使用 |
| `data/gold_template_exploration.jsonl` | 探索集人工审核答案模板，全部尚未审核 |
| `data/gold_template_holdout.jsonl` | 保留集人工审核答案模板，全部尚未审核 |
| `data/selection_manifest.json` | 抽样分组统计、题号和随机种子，保证两组不重叠 |
| `tests/test_pipeline.py` | 不依赖任何大模型和网络的单元测试 |

**这份包没有实际调用 AI、也没有擅自把模型预测写成人工金标准。**

## 初版标签数据处理（示意）

CF 原标签 `['binary search', 'data structures', 'dsu', 'graphs', 'greedy']`：

- `specific_tag_ids = ['binary_search', 'dsu', 'greedy']` → 二分、并查集、贪心。
- `provisional_tag_ids = ['pending_data_structures', 'pending_graphs']` → 数据结构·待细化、图论·待细化。
- `cf_unresolved_hints = ['data structures', 'graphs']` 等待 AI/人工分析。

AI 若仅明确了线段树，就把 `resolved_cf_hints` 填为 `{"data structures": ["segment_tree"]}`，数据结构临时标签移除，但图论临时标签仍保留。

注意该示例仅用来演示映射机制，不能断言某一道具体 CF 题使用线段树。

## 如何在 Windows Codex 使用

1. 解压到项目的独立实验目录，例如 `D:\ACM Project\ACM-Forever\experiments\tags_v0.3\`。**不要覆盖后端业务数据表**。
2. `cd /d "D:\ACM Project\ACM-Forever\experiments\tags_v0.3"`（CMD）；PowerShell 请使用 `cd "D:\ACM Project\ACM-Forever\experiments\tags_v0.3"`。
3. 在当前目录运行离线规则测试：

```powershell
python -m unittest discover -s tests -v
```

4. 预处理你们日后新爬取的 CF 和 ATC 题目：

```powershell
python label_pipeline.py prepare --input "D:\爬虫数据\codeforces.json" --output "my_cf_baseline.jsonl"
python label_pipeline.py prepare --input "D:\爬虫数据\atcoder.json" --output "my_atc_baseline.jsonl"
```

5. 用探索集 `data/exploration_inputs_20.jsonl` 和 `ai_annotation_prompt_v0.3.md` 让 Codex 生成**候选** `ai_predictions.jsonl`。该文件应有 `problem_key`、原样的 `content_hash`、`specific_tag_ids`、`resolved_cf_hints`、`provisional_tag_ids`、`reason`。
6. 运行合并与初评：

```powershell
python label_pipeline.py merge --base "data/exploration_rule_baseline_20.jsonl" --ai "ai_predictions.jsonl" --output "exploration_merged.jsonl"
python label_pipeline.py evaluate --predictions "exploration_merged.jsonl" --gold "data/gold_template_exploration.jsonl" --output "exploration_report.json"
```

此时人工模板中全是 `reviewed=false`，因此报告会提示**没有可计算准确率的人工标注**，这是正常情况。

7. 请两位有经验的队员分别标注关键题目，必要时参考已确认题解，由另一位复核形成最终 `accepted_specific_tag_ids` 和可接受的 `accepted_provisional_tag_ids`，再把 `reviewed` 改为 `true`。**人工标注必须根据证据完成，不得简单照抄 AI 输出**。之后再次评估。
8. 探索集可以用于迭代标签体系和提示词；**正式保留集先不要用于调规则**。冻结版本后才运行 60 道独立测试。建议先取得每题的人工答案，再检查 AI 结果，减少锚定偏差。

## 评估指标

- **具体算法 Micro-Precision / Recall / F1**：仅对人工确认的具体标签比较，保留集为主要汇报指标。
- **完全匹配率**：一题具体标签集合和人工参考答案完全一致的比例。
- **具体标签覆盖率**：有多少题得到具体算法标签。
- **临时标签率**：有多少题仍带至少一个「·待细化」标签。
- 人工审核比例、不同 OJ 的指标以及各类算法具体标签的错误分布需要另行报告。
- 现有 CF 官方标签可以作为**来源参考**，但官方的 `dp` / `data structures` 并不是「背包 DP」/「线段树」的人工真值；不得把「仅复用 CF 标签」的匹配率当成细分算法准确率。
- CF 与 ATC 做单独评估；CF 有官方标签的先验优势，混合总分容易掩盖 ATC 的真实错误。

## 边界 / 待定事项

- **模型未调用**：只是预处理、接口约定、样本和测试框架。预测值与准确率必须靠后续真实 AI 调用和人工审核获取。
- `content_hash` 必须随 AI 预测一起回传，防止标注过期覆盖更新过的题目；`human_confirmed` 结果拒绝自动覆写。
- 不修改 GitHub 主分支、数据库、爬虫或其他同学的业务模块。先在 `feat/forum-dev` 分支的独立实验目录内运行。
- 在「人工确认了题目的算法大类，但具体算法仍不确定」的情况下，人工金标准可以仅接受临时标签，不强行填具体标签。
- 当前包不包含牛客规则，因为用户尚未上传牛客原始爬虫格式，不能猜它的字段和标签体系。
