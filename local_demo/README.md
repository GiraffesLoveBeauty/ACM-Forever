# 标签与翻译的本地论坛验收服务

本服务复用论坛页面、爬虫题库结构和 Python 二次处理模块，单独提供接口；仅绑定 `127.0.0.1`，使用 `local_demo/runtime/forum-demo.sqlite3`，不连接正式数据库。详情见 [交付说明](../docs/algorithm-tagging-delivery.md)。

## 安装与启动

在仓库根目录运行（Python 3.12+，Node 22.13+）：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r local_demo/requirements.txt
Push-Location feat/web
pnpm install --frozen-lockfile
pnpm build
Pop-Location
.\start-local.ps1 -Background
```

打开 <http://127.0.0.1:18088/admin.html?section=problems>。默认本地合成管理员 `1` / `Local-Tag-Admin!2026`；普通合成用户 `10000001` / `Local-Demo-Only!2026`。这些默认账号仅供回环地址验收，不能部署到公网。

停止：` .\stop-local.ps1 `。前台启动：` .\start-local.ps1 `，Ctrl+C 停止。

首次启动没有题库与标签数据，正常显示空列表；PR 不包含真实题面、已付费结果、人工历史、账户、数据库或密钥。可用下面的明确操作添加临时合成验收题，或自行指定合法的本地采集数据。它不会调用 API，也不会覆盖已有标签目录：

```powershell
.\.venv\Scripts\python.exe -B local_demo/seed_synthetic.py
```

合成题的熟悉 OJ ID 仅测试身份映射，题目与译文均是模拟内容。

## 操作边界

### 翻译没有返回结果时

- 图片默认留在本地结构中，翻译周围文字；图片本身不会触发文字翻译阻断。算法标签是否能理解图意是另一个任务。
- 发送前本地校验失败、DNS/TCP/TLS 连接建立失败：新记录为 `failed_before_dispatch`，生成请求未发出。不会自动重试，重新预检后用户可以明确再次发起；之前的回执保留。
- 写入/读取超时或无法证明未发送的异常：保持 `uncertain`，是否计费未知，禁止自动重发。历史未知记录不会因为代码升级改判为“未发送”。
- 已返回但解析/文字 ID 回填失败：保留原始响应和返回的用量，停止发布。原文、原图和旧译文不覆盖。
- 页面按任务类型分别显示标签/翻译回执。图片说明不会覆盖真正的网络或历史请求阻断原因；本地请求尝试数不代表中转站接收数或实际收费笔数。

### worker 退出与遗留任务恢复

服务启动、提交任务（包括重复提交）和读取任务状态时，会核对遗留的 `queued/running` 回执。新排队任务有 15 秒启动窗口；随后必须同时取得 worker 锁、同题协调锁和 Ledger 任务锁，才允许收尾。锁由操作系统在进程退出时释放；不会根据 PID 或超时认定请求没有发送。延迟启动的 worker 取得锁后会重读回执，已终止的任务不会再发请求。

- 尚未领取或只完成领取：保存 `blocked` 回执及恢复依据，Ledger 中的 `claimed` 转为 `blocked`，不自动重发。
- 已登记发送、没有可靠的持久响应：Ledger 和网页回执转为 `uncertain`，原任务继续禁止自动重发，但不再占用其他题目的全局执行位置。
- 已保存响应但尚未完成发布：保留响应，转为 `blocked` 等待核验；响应损坏时为 `uncertain`，不自动解析、发布或补发。
- Ledger 已完成且结果绑定和哈希有效：修复丢失的成功回执与用量，不重新调用 API。

回执的 `recovery` 保存原网页状态、恢复时间及 Ledger 任务/尝试的前后状态。新 worker 从首次领取检查点起记录任务与尝试 ID；旧回执仅保守关联排队后产生且配置一致的尝试，不能把更早的成功结果当作本次成功。恢复无法确认实际调用笔数时返回 `real_api_calls=null`，费用仍须核对中转站账单。恢复不替代原任务的人工核验，也不会解锁其未知请求。

- 管理后台 → 题库管理：查看采集数据、预检标签/翻译任务、保存人工覆盖与撤销。仅 admin/root 可以执行。
- 成员题库：有效标签筛选，保留原始标签；题目页展示原文、已激活译文、标签来源及样例复制。
- AI 请求需管理员逐题确认，并从本仓库实验模块 `.env` 读取专用配置；缺少配置时只展示预检。示例配置无 Key，不继承环境中的认证变量，不读取其他项目。
- 目前固定允许 `https://kitsune2.yukirin.me/v1` 与 `gpt-6-luna`；JSON Schema/token 参数需服务商支持。每题最多一个请求、SDK/应用重试 0、超时 90 秒、输出上限 4000。执行前重查状态并加跨进程锁；未知结果不会自动重发。
- 自动翻译使用 `layout_by_id`：本地保留规范化段落、图片、公式、代码和样例，仅发送文字片段，AI 按 ID 返回，本地回填。只检查 ID 完整性，不进行准确性、数字或中文覆盖率审核；旧 `parse_only` 结果继续显示。仅因图片待处理的题目可以翻译周围文字，图片内文字不翻译，标签仍需图片复核。PDF 等输入预检、权限和防重复计费保护继续生效。详见 [翻译协议](../experiments/tags/ACM_Forever_Chinese_Tags_V0.3/README_TRANSLATION_VALIDATION.md)。
- 主服务拒绝非回环网络；显式确认后的独立 AI worker 才可访问指定服务商。未确认不自动采集、不自动调用 AI。
- `collect_atcoder_local.py` 是显式联网采集入口，仅写本目录固定的本地测试库，不调用 AI；本轮交付测试未执行采集。
- 不向正式服务自动注册这些本地扩展接口。不能把本地验收视为生产部署完成。

## 离线测试

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s local_demo -p 'test_*.py'
Push-Location experiments/tags/ACM_Forever_Chinese_Tags_V0.3
& ../../../.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p 'test_*.py'
Pop-Location
Push-Location feat/web
pnpm test
pnpm build
Pop-Location
```

集成测试动态构造临时合成标签、译文和 SQLite，不依赖开发者私有的 10 题快照；`httpx.MockTransport` 不发出网络请求。历史离线严格翻译审计工具 `translation_release.py` 仅处理已保存响应，自动翻译不经过该审计工具。
