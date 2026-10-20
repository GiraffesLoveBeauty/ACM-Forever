# Git 本地归档范围

本次归档包含独立标签/二次处理工具、V0.3 词表及 CF 映射、209 项离线测试、模拟样本、文档、依赖声明和无密钥配置模板。没有归档真实 API 预测、持久数据、人工事件或备份。

## 本地数据保留与排除

本机的 `data/` 包全部保持原文件，并由模块 `.gitignore` 排除。本次仅检查格式、许可字段与是否存在已审核答案，没有标注、评估或重新生成留出集。

| 本地文件 | 排除原因 |
|---|---|
| `exploration_inputs_20.jsonl` | 20 道完整第三方题面，含 9 条已匹配题解；未取得可确认的再分发许可 |
| `holdout_inputs_60.jsonl` | 60 道完整第三方题面，含 26 条题解；许可待确认，且应独立保存以防评估污染 |
| `gold_template_exploration.jsonl`、`gold_template_holdout.jsonl` | 本地人工评估模板；目前 reviewed 均为 false，不作为公共训练或正确答案数据 |
| `holdout_rule_baseline_60.jsonl`、`selection_manifest.json` | 包含正式留出集的标签先验或分组身份，应与评估数据一起独立管理 |
| `exploration_rule_baseline_20.jsonl`、`atcoder_baseline_all.jsonl`、`codeforces_baseline_all.jsonl` | 爬虫批次派生数据，与本地原始数据包统一管理，不混入源码归档 |
| `example_evaluation_before_review.json` | 本地数据包的示例报告，随整个包保留；不影响单元测试 |

OJ 题目公开可访问不表示可以完整再分发。本地仓库与交接说明没有提供适用的许可或共享约定；本地 Git 配置也不能证明 GitHub 仓库可见性。本次没有执行远程可见性查询、fetch、push 或创建 PR。数据共享需团队另行确认仓库可见性、适用平台条款和独立留出集的访问范围。许可确认前不要强制添加被忽略的真实数据。

`tests/fixtures/translation_samples.jsonl` 是具有 `offline` 身份的人工构造加法示例，其余测试使用 Mock 数据、临时目录和 MockTransport。这些模拟样本可随源码归档，既不是正式 OJ 题目，也不是付费 AI 结果。

## 新电脑运行

在模块目录创建本地虚拟环境，安装 `requirements-api.txt` 后运行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
```

测试不需要 API Key，不需要本机 `data/` 或 `data/labels`。CLI 的真实数据示例引用本地探索集，其他开发者需使用自己拥有使用权限的数据路径。不要为了让示例运行而从共享渠道传播留出集或真实人工答案。

原输入筛选测试已改用临时构造的 10 道 CF 与 12 道 AtCoder 样本，继续验证只选择前 10 道 AtCoder；原始探索集保持不变。提交前还会在仅含拟归档文件的隔离副本中运行全部测试，以确认没有遗漏本机数据依赖。

`.env.example` 保留通用模板，Key 和模型均为空；复制到被忽略的 `.env` 后按实际服务商填写。进行任何真实 API 操作仍须单独授权，不能将测试中的假凭据作为真实 Key。

## 忽略与归档约定

忽略 `.env`、虚拟环境、缓存、运行输出、日志、写锁、临时文件、模块内备份/恢复目录、整个本地数据包和实际人工记录。保留 `manual_labels/settings.json` 的便携式 `storage: persistent` 配置，不写入开发者专属路径。

项目根目录的 `data/labels` 已由根 `.gitignore` 忽略。正式备份位于仓库外，不能用 Git 归档源码代替标签、人工事件与翻译数据备份。不要执行 `git clean -x` 删除这些本地资产。
