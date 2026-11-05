# 人工标签修正与有效标签查询

阶段 6C 的本地管理工具，不调用 API，也不改写词表、论坛、数据库或原始预测。
默认使用成功的自动标签；自动生效不等于人工确认。推荐模块应统一查询本模块的 effective_tags。
没有新增第三方依赖，使用 Python 标准库和现有 V0.3 的校验、身份解析及 CF 映射。

## 文件与默认来源

```text
manage_tags.py                     中文 CLI
tag_management/
  __init__.py                     导出 TagManager / get_effective_tags
  model.py                        ID/中文名称解析、集合状态、确认指纹
  storage.py                      JSONL 历史、原子替换、跨进程写锁
  service.py                      自动来源适配、人工操作、有效标签查询
manual_labels/
  settings.json                   明确指定自动结果文件
  .gitignore                      忽略本地历史和锁/临时文件
  overrides.jsonl                 首次有效人工操作时创建，不随输出/缓存清理
tests/test_manual_tags.py          临时目录里的模拟数据与文件/CLI测试
README_MANUAL_TAGS.md
```

阶段 7B 后 `settings.json` 默认使用独立持久目录 `data/labels/catalog/current.json`，
支持 `TAG_DATA_ROOT` 覆盖，不依赖实验 outputs。旧 schema_version=1 + auto_file 配置仍兼容。
不会自动选“最新模型”。`--auto-file` 可以临时指定其他 merged_results/predictions 文件，
Python 接口可用 `auto_file=` 指定；以后更换模型运行目录，只更新这个来源指针或参数。
同一个题目的跨模型自动结果不能混在同一来源文件内；重复身份、非法 ID 或标签版本不符会报错。

默认人工历史为持久根目录的 `manual/overrides.jsonl`；旧模式仍使用 manual_labels/overrides.jsonl。
两个位置都独立于 outputs/cache，没有任何命令修改 predictions.jsonl。
建议定期将整个 manual_labels 备份到独立位置。被 Git 忽略不代表它是可丢弃缓存；
不要使用 `git clean -x` 清理该目录。自定义 `--overrides` 也禁止位于 outputs/cache 或题目输入目录。

## PowerShell 命令

```powershell
Set-Location -LiteralPath 'D:\ACM Project\ACM-Forever\experiments\tags\ACM_Forever_Chinese_Tags_V0.3'
$tagPython = '.\.venv\Scripts\python.exe'

# 查看：原始 CF 标签、自动结果、人工集合、最终中文标签、来源和状态
& $tagPython -X utf8 manage_tags.py show 'atcoder:abc475:abc475_d'

# 示例操作会真实写入人工记录，请按实际人工判断选择标签
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '人工补充算法依据' add 'atcoder:abc475:abc475_d' '枚举'
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '人工确认不适用' remove 'atcoder:abc475:abc475_d' 'sieve'
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '人工更正示例' replace 'atcoder:abc475:abc475_d' 'enumeration' 'simulation'

& $tagPython -X utf8 manage_tags.py history 'atcoder:abc475:abc475_d'
& $tagPython -X utf8 manage_tags.py list

# 撤销该题最近一次操作，历史仍保留；连续 undo 会撤销上一条 undo，因此可形成重做
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '撤销上次操作' undo 'atcoder:abc475:abc475_d'

# 撤销所有当前人工覆盖，恢复当前来源文件里的自动标签，而不是旧版本标签
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '恢复自动结果' reset 'atcoder:abc475:abc475_d'

# 可选：只有完整检查过当前最终标签时才执行；不是自动流程
& $tagPython -X utf8 manage_tags.py --actor '同学A' --reason '已完整检查主解法和标签' verify 'atcoder:abc475:abc475_d'
```

全局参数放在子命令之前。add/remove 可一次输入多个 ID 或中文名称；内部统一存 ID。
不在词表中的标签拒绝写入。add/remove/replace 重复执行且状态不变时不会新增历史。
replace 的 A 必须是有效标签，或已经完成同一 A→B 替换；A、B 必须不同。

添加已有自动标签有明确含义：将该标签固定为人工添加，后续 AI 不再给它时仍保留。
删除当前不存在的合法标签也有明确含义：记录禁用，防止后续 AI 自动加入。
对同一 ID 的反向人工操作会清除另一集合中的该 ID，不会同时增删。
CF 精确映射允许通过 remove/replace 明确纠错，操作前快照会保留 raw_tags 和 cf_rule_mapping 来源。
默认 actor 是 local_admin；本地 CLI 不进行身份认证，不可直接暴露为公开服务。

## 三层数据与持久化

```text
有效 ID = (当前自动 ID ∪ 人工添加 ID) - 人工删除 ID
```

人工 ID 集合互斥、去重，使用词表顺序稳定输出。成功的空预测合法；结果可以为空。
人工新增和禁用集合独立于模型指纹及自动运行目录，仅以规范 problem_key 关联题目。

JSONL 每行是一条不可删除的逻辑事件。示例（格式化展示，实际存储为单行）：

```json
{
  "schema_version": 1,
  "event_id": "示例唯一事件ID",
  "previous_event_id": null,
  "problem_key": "atcoder:abc475:abc475_d",
  "operation": "remove",
  "created_at": "2026-10-09T13:00:00+00:00",
  "actor": "同学A",
  "reason": "人工确认该标签不适用",
  "taxonomy_version": "0.3-draft",
  "before": {
    "added_tag_ids": [], "removed_tag_ids": [],
    "anchor_content_hash": null, "verified_fingerprint": null
  },
  "after": {
    "added_tag_ids": [], "removed_tag_ids": ["sieve"],
    "anchor_content_hash": "首次人工修正时的题面哈希", "verified_fingerprint": null
  },
  "automatic_snapshot": {
    "problem_key": "atcoder:abc475:abc475_d",
    "tag_ids": ["enumeration", "sieve"],
    "origins": {"enumeration": "ai", "sieve": "ai"}
  },
  "details": {"tag_ids": ["sieve"]}
}
```

实际 automatic_snapshot 还保存题目身份、题面哈希、标签中文信息、模型、版本、原始 CF 标签及旧审核状态。
before/after 使撤销无需再次调用模型。reset/undo 本身也追加事件，不删除历史。
previous_event_id 连接全局事件序列，读取时校验重复事件、状态连续性和 ID 集合合法性。
该链用于检测结构损坏，不是防管理员恶意篡改的密码学签名。

每次写入先获取 OS 文件锁，再读取最新历史和自动结果，在同目录临时文件写完整历史，
flush + fsync 后用 os.replace 原子替换。其他写进程拿不到锁会直接报错，不丢失更新。
损坏/截断历史不会自动修复或覆盖；应从备份恢复。首版适用于本地小规模历史，写入成本与历史长度相关。

## 统一查询接口

```python
from tag_management import get_effective_tags, TagManager

result = get_effective_tags("atcoder:abc475:abc475_d")
ids_for_recommendation = result["specific_tag_ids"]
if not result["recommendation_eligible"]:
    # 交给异常队列，保留现有人工修正，不自动删除或重跑
    pass

manager = TagManager(auto_file="其他自动结果.jsonl", override_file="独立目录/overrides.jsonl")
result = manager.get_effective_tags("atcoder:abc475:abc475_d")
```

返回数据包含：auto_tags、manual_overrides、effective_tags、具体/临时 ID 与中文名称、审核状态、
needs_review_reasons 和 recommendation_eligible。每个 effective_tags 元素有 id、name_zh、tag_kind、source、sources；
sources 保留同时来自自动和人工添加的信息，source 表示当前优先来源。
来源区分 ai、cf_rule_mapping、manual_add 和 legacy_human，自动生效不会伪装成人工。
既有预测文件使用 evaluation_* 合并字段时直接读取它们；CF 精确标签仍复用 prepare() 按 raw_tags 恢复，
最终允许人工禁用覆盖。推荐系统通常只使用 specific_tag_ids；临时大类供展示和后续细化。

持久模式每次新建管理器读取已提交的当前版本，批量接口一次加载自动标签与人工历史。
旧显式文件模式仍支持读取指定来源。详细导入、批量和翻译说明见 README_SECONDARY.md。
不在 annotate_api 内修改合并逻辑，因此缓存指纹、旧原始文件及旧评估行为保持不变。

## 新旧状态兼容

| 查询层状态 | 含义 | 推荐可用 |
| --- | --- | --- |
| auto | 成功的自动结果，没有人工覆盖；历史 pending_review 在此映射 | 是 |
| corrected | 存在人工增删，但未完整确认 | 是 |
| verified | 显式 verify，或旧 human_confirmed/approved/reviewed=true | 是 |
| needs_review | 调用失败/未知、明确异常、人工锚点题面变化或完整确认后自动结果变化 | 否，进入异常队列 |

此策略只在新查询层生效，绝不批量改写旧 review_status/human_review_status。
人工修正后题面哈希变化时，继续按集合公式返回最终标签，保留人工集合，标记 needs_review。
后续普通 add/remove 不会把锚点悄悄更新；完整重新检查后可以 verify，或明确 reset 放弃人工覆盖。
缺少人工修正关联的题面哈希时同样提醒复核。成功的空标签、临时大类本身不强制进入人工队列。
自动结果中的非法 ID/重复身份/版本不一致直接报错，避免返回可用于推荐的错误结果。
切换来源后消失的题目仍能通过 list/history 找到人工记录，list 标记 automatic_problem_missing。

corrected 不是人工完整金标准；auto 更不是。现有 evaluate_api 仍仅接受人工 reviewed=true 的标准答案，
本工具不生成 reviewed=true，不使用有效标签或模型预测计算所谓正确率。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p test_manual_tags.py -v
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests
```

新增测试只在临时目录使用模拟题目；覆盖标签增删替换、重复操作、AI 更新保护、CF 精确标签纠错、
空标签、非法 ID、恢复/撤销、历史持久化、跨题目隔离、题面变化、状态兼容、原子写失败及写锁。
开发验收没有实际修正阶段 6B 的 10 道题目，也没有创建真实人工记录。

## 以后接入管理员页面

1. 展示 get_effective_tags 的三层数据、来源、异常原因和历史。
2. 后端认证管理员并填写真实用户 ID 作为 actor，校验原因、标签和当前事件版本；不可信任前端自报权限。
3. 页面操作调用 change，推荐服务只读此查询接口；读写服务共享同一个持久人工来源。
4. SQLAlchemy 迁移时分别保存题目自动版本、人工事件和当前覆盖状态，以 problem_key 关联，
   用事务/乐观锁替代本地文件锁，并保留 JSONL 事件 ID、时间、actor、reason、before/after。
5. 迁移后保留此查询返回结构和集合公式，不把人工结果写回 AI 原始预测。

本阶段不新增论坛接口或数据库迁移。
