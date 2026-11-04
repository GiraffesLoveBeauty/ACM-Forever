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

- 管理后台 → 题库管理：查看采集数据、预检标签/翻译任务、保存人工覆盖与撤销。仅 admin/root 可以执行。
- 成员题库：有效标签筛选，保留原始标签；题目页展示原文、已激活译文、标签来源及样例复制。
- AI 请求需管理员逐题确认，并从本仓库实验模块 `.env` 读取专用配置；缺少配置时只展示预检。示例配置无 Key，不继承环境中的认证变量，不读取其他项目。
- 目前固定允许 `https://kitsune2.yukirin.me/v1` 与 `gpt-6-luna`；JSON Schema/token 参数需服务商支持。每题最多一个请求、SDK/应用重试 0、超时 90 秒、输出上限 4000。执行前重查状态并加跨进程锁；未知结果不会自动重发。
- 按项目当前策略，自动翻译使用 `parse_only`：恢复已知占位符并解析非空正文，不进行翻译准确性或公式语义审核。标签 ID、图片/PDF 输入预检、权限与防重复请求校验继续保留。译文不等同人工确认。
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
