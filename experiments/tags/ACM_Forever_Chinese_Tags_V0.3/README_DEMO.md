# 本地验收 Demo

独立生成可直接打开的简体中文 HTML，不需要 Vue、Web 服务、网络或新增依赖。
默认只读真实数据；人工操作及翻译演示只使用临时模拟目录。

## 生成与打开

在 PowerShell 中执行：

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'
.\.venv\Scripts\python.exe -B -X utf8 demo_acceptance.py --run-tests
Start-Process -FilePath '.\demo_generated\index.html'
```

也可以双击 `demo_generated/index.html`，浏览器直接通过 `file://` 打开。
无 `--run-tests` 时仅生成页面；显示本工具已经保存的测试记录、运行日期和源码匹配状态。
没有记录则显示“未运行”，不会自动沿用历史的 209 项测试结论。
测试失败时保存真实失败摘要并返回非零退出码。

页面支持题号/题名/标签搜索、按有效标签和人工状态筛选，以及展开题目详情。
展示的是生成时的数据快照，数据变化后需重新生成。

## 数据来源及展示边界

| 区域 | 读取来源 | 展示含义 |
| --- | --- | --- |
| 词表及中文名称 | `tag_taxonomy_v0.3.json` | 实际标签数量，不生成新标签 |
| 题目与自动标签 | `Repository` 当前目录版本及 `auto_tags.jsonl` | 已持久化的自动标注，不读取或改写实验 `outputs` |
| 有效标签/人工状态 | `TagManager.get_effective_tags_many()` 及独立人工事件日志 | 自动结果默认生效，不等于人工确认或正确答案 |
| 真实翻译数量 | 当前题目对应的有效翻译索引 | Mock 不计入；无真实译文则为 0 |
| 人工修正四步演示 | 临时合成题、真实管理模块操作 | 初始枚举 → 添加前缀和 → 删除枚举 → reset，临时历史使用后清理 |
| 翻译演示 | `tests/fixtures/translation_samples.jsonl`、现有 Mock 客户端 | 英/日文展示实际 Mock 返回，中文跳过；不是付费 AI 翻译成果 |
| 备份及恢复证据 | 配置的备份根目录、相邻 `audits` 及报告指向的既有隔离目录 | 本次只读重验 SHA-256；匹配 manifest 后重新比较当前数据与隔离恢复数据 |
| 测试 | `demo_generated/test_report.json` | 实际计数、日期、耗时、网络阻断记录及源码摘要 |
| Git | 本地 `git branch` / `rev-parse` / `status` | 当前分支、完整提交哈希与是否存在未提交更改 |

持久目录默认沿用 `data/labels` / `TAG_DATA_ROOT`，备份路径沿用现有 `backup_root()`。
可指定只读来源：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 demo_acceptance.py --data-root 'D:\path\labels' --backup-root 'D:\path\backups'
```

`--output` 只允许写入模块 `demo_generated/` 下的 HTML；该目录已加入 Git 忽略规则。
备份缺失、损坏或历史隔离目录不可用时明确显示相应状态，不创建备份、不恢复或替换活动目录。
历史恢复报告必须绑定备份路径及 manifest SHA-256；报告日期与本次校验明确分开。

## 安全与离线验证

- 脚本不加载 `.env`，不创建真实 API 客户端，不连接数据库。
- `--run-tests` 在子进程中阻断 socket 连接及真实 HTTP transport；Mock transport 保持可用。
- 页面只导出题目身份、名称、原站链接、标签、来源、模型、依据及相关追溯元数据。
  不打包真实题面全文、题解、私有留出集、原始 API 响应或认证配置。
- 外部文本/属性统一 HTML 转义；官方 OJ 链接执行域名白名单检查，去掉查询参数与片段。
- 页面没有 CDN、外部字体或在线公式依赖；CSP 禁止网络请求。
  用户主动点击原题链接会打开原站，属于离开本地 Demo。
- 模拟翻译按原始 Markdown 展示公式和代码，便于核对原样保护，不宣称中文翻译质量。
- 产物含真实题目元数据及本地路径，只应在团队授权范围内分享，不应提交 Git。
- 不计算缺少人工标准答案的标签准确率；不宣称完成论坛或推荐系统接入。
- 7E 已完成新爬虫格式离线适配；7F 增加当前持久题目的独立标签 / 翻译规划展示。
  真实新爬虫正文导出的联调尚缺本地数据。7G 已将付费入口接入安全执行器，完成发送前重检、任务锁和未知结果阻断的离线验证。
  页面仍然只读，不会执行任务；上游恰好计费一次的能力未得到验证，见 `README_SAFE_EXECUTION.md`。
- 页面「增量处理」区域调用 `Planner` 只读比较题目、自动标签、人工修改、翻译索引与旧请求证据；
  每项任务可复用、缺失或待核验的状态均来自本次规划，不执行任何 AI 任务。
- 完整端到端操作顺序及安全边界见 `README_PROCESSING_PLAN.md`。

## 建议的五分钟演示

1. 0:00—0:45：概览统计、Git 版本、真实与 Mock 的边界。
2. 0:45—2:00：筛选真实标签并展开一题，查看算法依据、来源和未人工确认状态。
3. 2:00—3:00：隔离人工修正四步，说明删除优先级与重置。
4. 3:00—4:00：英/日文 Mock 翻译及公式、代码保护，中文跳过与真实翻译数量。
5. 4:00—5:00：备份哈希和隔离恢复一致性、实际测试结果、尚待完成的能力。
