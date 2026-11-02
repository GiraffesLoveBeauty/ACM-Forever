# 浏览器回归测试

测试通过真实的 Vue 生产构建和 Quart API，分别在桌面和移动视口验证：公开论坛、登录后返回编辑器、普通成员权限、两次 Markdown 导入、草稿刷新恢复，以及提交审核 → 发布 → 评论 → 回复 → 作者删除。

从仓库根目录安装 Python 依赖：

```sh
python -m pip install -r feat/api/requirements.txt
cd feat/web
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
pnpm build
pnpm test:e2e
```

可用环境变量：`ACM_E2E_PYTHON` 指定 Python 可执行文件，`ACM_E2E_BROWSER` 指定已有 Chromium/Edge 可执行文件，`ACM_E2E_PORT` 修改默认的 18761 端口。PowerShell 示例：

```powershell
$env:ACM_E2E_PYTHON = 'D:\path\to\venv\Scripts\python.exe'
$env:ACM_E2E_BROWSER = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
pnpm test:e2e
```

启动器仅监听 `127.0.0.1`，自动创建临时 SQLite 和合成测试账号，清除继承的 `ACM_*` 服务配置并关闭同步任务。不会读取现有数据库。服务由 Playwright 管理，不复用已经运行的服务，端口被占用会直接失败。正常退出时清理临时数据，强制终止可能在系统临时目录留下 `acm-browser-tests-*` 文件夹。

每个用例使用独立浏览器会话；桌面和移动用例顺序运行。没有固定延时，等待的是页面状态或 API 完成。失败时保存截图、trace 和 HTML 报告；可用 `pnpm exec playwright show-report` 查看。GitHub Actions 自动执行同一命令，并在失败时保留产物 7 天。测试账号密码仅用于每次新建的临时环境，不能用作正式账号凭据。
