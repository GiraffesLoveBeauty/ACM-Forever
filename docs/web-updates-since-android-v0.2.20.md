# 网站更新核对：Android v0.2.20 之后

状态：2026-11-06 只读核对仓库代码。本轮不修改网页、后端或服务器，不上传 PR；生产部署及实际数据尚未验证。

比较基线：已发布 `v0.2.20`（`b6a9bfe9171cbb55be6b25b9f03d6424489899b6`）至本次核对的 `main`（`040bfb3ce7a55c08cbf23ac066eadb4a50cf1426`）。新增 [PR #109（全员 AC 定时同步与 CF 比赛目录补全）](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/109)，实现提交 `ed155b9`，共 13 个文件、增加 986 行、删除 92 行。

## 新增与改进

| 更新 | 具体行为 | 对 App 的影响 |
| --- | --- | --- |
| 全员定时同步 AC | 默认每 60 分钟同步正常且绑定 OJ 的成员，启动时补跑到期任务；首次拉取可获取的历史记录，以后按成功游标增量同步并回看最近七天；某成员或平台失败继续处理其他成员 | 已有通过题数、排行榜、最近 AC 等复用相同后端数据，部署后可直接受益；不需要新增 App API |
| AtCoder 历史记录分页 | 从单次请求改为按提交时间分页，每页最多 500 条，边界秒重复读取并按题去重；限制请求频率，分页异常时不推进成功游标 | 历史记录较多的成员可补齐过题数据；不需要新页面 |
| Codeforces Div.1/Div.2 比赛题目录补全 | 从官方 standings 保存各场比赛自己的完整题号和顺序；补齐同轮、同开始时间的配对赛事，避免共用题目导致目录残缺；完整目录缓存七天，重新拉取可刷新 | 题库和比赛进度复用完善后的目录；旧库需管理员重新运行 CF 全平台采集，合并代码本身不会立刻补齐全部旧数据 |
| 后台显示成员同步进度 | 同步任务显示“已处理 X / Y 位成员”，可查看“全员定时同步”任务与取消状态 | App 已支持通用 done/total 进度，可显示基础数量；本轮未专门适配成员单位文案 |
| 后台显示比赛目录补全进度及失败详情 | 题目采集增加“正在补全比赛题目列表 X / Y 场”，列出补全失败的比赛与错误 | App 管理页尚未识别新 `contest_catalog` 阶段和目录失败列表，可作为后续适配项；本轮只记录 |

本次没有新增普通用户论坛、搜索、主题或个人中心页面，也没有新增供 App 使用的独立业务路由。主要是共享后端数据完整性与管理员任务可见性改进。

## 已合入、但早于上述比较基线的题面翻译与标签功能

补充核对：题面翻译相关代码已在 2026-11-05 随 [PR #91](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/91) 合入 main（`b27c2334c933872e60c2c8c761d20803c356c167`），早于 v0.2.20。前面的五项只列 v0.2.20 之后的增量，不能据此判断网站没有翻译功能。

| 能力 | 网页与工具代码 | 正式服务 / App 状态 |
| --- | --- | --- |
| AI 中文题面翻译 | 管理员逐题预检、确认执行、保存译文；成员题目页读取已激活译文，可展开/收起，保留爬虫原文 | 路由目前注册于 `local_demo`，尚未接入 `feat/api` 正式服务；App 尚未读取该翻译结果 |
| 保留原题结构 | 本地保存图片、公式、代码及样例，AI 按文字 ID 翻译后回填；图片内文字不翻译 | 不代表所有题都已有译文；译文标记未人工确认，PDF/图片/ZIP 等输入仍有处理边界 |
| 中文算法标签 | CF 标签映射、AI 标注、最终有效标签及来源/审核状态展示，用于本地题库筛选 | 与原题库标签并非自动完成正式整合；App 尚未读取二次处理标签 |
| 人工修正与审计 | 标签增删、替换、撤销、版本冲突检查、历史与备份；管理员统一处理面板 | 手机便捷管理尚无这些操作；正式鉴权、持久目录及路由集成仍需完成 |

成员查看已保存译文不会自动调用 AI 或触发付费翻译。当前 Android 题面页读取 `statement_html` / `statement_text`，没有原文/译文切换或二次处理结果区域。若要接入，需要先把现有本地接口整合到正式后端，再在 App 复用，不能把本地验收路由当成线上可用接口。

依据：[交付与正式接入边界](algorithm-tagging-delivery.md)、[成员题面组件](../feat/web/src/components/SecondaryProcessingPanel.vue)、[管理员处理组件](../feat/web/src/components/AdminProblemProcessing.vue)、[本地结果读取路由](../local_demo/server.py)、[本地管理员路由](../local_demo/admin_processing.py)与[执行路由](../local_demo/ai_execution.py)。本次只读检查与补充文档，未执行 AI 请求、修改后端或改动 APK。

## 配置与运行条件

- `ACM_MEMBER_SYNC_ENABLED` 默认 `true`，设为 `false` 可关闭全员自动同步。
- `ACM_MEMBER_SYNC_INTERVAL_MINUTES` 默认 `60`，允许 `1–1440` 分钟。
- 成员同步保留平台启用状态与洛谷暂停策略；等待其他后台任务空闲后安排，不抢占正在执行的任务。
- 上次自动启动时间保存到 SQLite，服务重启据此判断是否到期；部分失败不等于所有成员均已成功同步。
- CF 完整目录使用新增的 `crawler_contest_catalogs` 缓存表；已有题面、样例和用户记录继续保留。上线备份、部署及旧库补采由管理员安排。

## 源码位置

| 位置 | 内容 |
| --- | --- |
| [service_runtime.py](../feat/api/service_runtime.py) / [app.py](../feat/api/app.py) | 调度、任务状态、环境变量和启动集成 |
| [sync_service.py](../feat/api/acm_api/sync_service.py) / [crawler.py](../feat/api/acm_api/crawler.py) | 成员增量同步与 AtCoder 分页 |
| [cf_contest_catalog.py](../feat/api/acm_api/cf_contest_catalog.py) / [problem_sync.py](../feat/api/acm_api/problem_sync.py) | CF 完整目录获取、缓存及采集接入 |
| [problem_bank.sql](../feat/api/acm_api/problem_bank.sql) | 比赛目录缓存表 |
| [Tasks.vue](../feat/web/src/admin/Tasks.vue) | 成员同步任务进度 |
| [ProblemTaskProgress.vue](../feat/web/src/components/ProblemTaskProgress.vue) | 比赛目录阶段与失败详情 |
| [README.md（后端运行说明）](../feat/api/README.md) | 同步开关、间隔和补采说明 |

此次只读核对确认功能代码已进入上述 main 版本，没有登录生产后台、触发真实采集或运行新增后端测试，不能据此判断线上数据已经补齐。
