# Web 加载性能采样与验收

本工具用于 Issue #54 的分阶段排查，以及 Wiki 加载优化发布前后的同条件对照。不登录、不写业务内容，不保存账号、Cookie、帖子正文、截图或用户资料。匿名访问帖子详情会按正常阅读增加浏览量。网络调整前后的历史基线缺失时，不能补造「调整前」数据，也不据此归因 Tailscale 或带宽。

## 运行

先在 `feat/web` 按锁文件安装依赖，并安装 Playwright Chromium（或用 `--browser` 指定本机 Chrome/Edge）。输出文件放在仓库外或被忽略的 `data/`：

```powershell
cd feat/web
pnpm install --frozen-lockfile
pnpm exec playwright install chromium
node tools/performance-audit.mjs --site https://acm.cjluacmpanle.top --site https://cjluacmpanel.tail1b9e55.ts.net --samples 3 --output ../../data/performance.json
```

Windows 也可追加 `--browser "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"`。仅接受不带账号、路径和查询串的 HTTP/HTTPS 根地址；支持 1–10 个样本，不忽略 TLS 证书错误。预期这是少量串行采样，不是负载测试。访问真实帖子会产生正常阅读统计。

默认覆盖论坛、Wiki、排行榜入口，以及自动选择的第一篇公开帖子和 Wiki 文章；同一次执行固定选择，便于重复采样。无公开条目则跳过文章场景。冷缓存指新的浏览器上下文，热访问指同上下文 reload；这不代表清空了服务器缓存、操作系统 DNS 或 TLS 会话。浏览器以匿名桌面 1440×900 运行，不降速，不模拟登录用户。

每个场景记录实际目标内容出现时间、FCP、采样窗口内 LCP、同源 Resource Timing、资源传输字节、API 次数、请求失败、HTTP 错误与横向溢出。`staticBytes` 仅合计 `/assets/` 的传输字节；`/uploads/` 图片仍可在资源明细中单独检查，不包含在该合计中。分列 DNS、连接、TLS、TTFB、下载阶段；连接耗时包含 TLS，不能将两列相加。连接复用时相应字段可为 0。网络最多额外等待 5 秒，之后仍在加载的资源可能没有完整 timing，LCP 是窗口内值而非完整用户会话最终值。

另测 `/health`、论坛分类、帖子列表、Wiki 目录的独立匿名 HTTP 请求，记录端到端耗时与 `Server-Timing`；这组数据包含独立请求建立连接的时间，不能直接当作浏览器连接复用下的后端处理时间。工具不保存响应正文。

JSON 汇总提供成功数、中位数与最近秩 p95，失败与缺失值不计入成功耗时。只有 3 个样本时 p95 等于最慢样本，只用于定位波动，不能代表长期服务指标。出现导航或探测失败时保留报告并返回非零退出码；资源错误单独保留，应检查是否为正常取消、超时或服务器错误。

## 如何判断慢点

- 同场景比较两个入口，核对文档连接、TLS 与 TTFB，不能把入口差异直接解释成某一条链路故障。
- API TTFB 偏高时结合 `Server-Timing` 与服务器日志判断；缺少 Server-Timing 不能从浏览器推算 SQL 耗时。
- 冷访问传输量和静态资源时间明显高、热访问恢复时，检查缓存头、压缩、字体和脚本体积，再通过同一工具复测。
- 布局溢出字段只覆盖所访问页面及视口，手机和主题变化需另做浏览器回归。

发布前后应使用同一设备、浏览器、网络、场景与样本数，记录已部署提交及测量时间。此工具不会部署，也不会把开发分支直接当作生产版本。#54 的历史网络调整状态、调整前耗时和真实生产提交需要由运维核实；本 PR 只提供可复用采样与当前入口基线。

## 本地检查

`node --test tests/performance-metrics.test.mjs` 验证失败样本、百分位、参数及阶段计算；`pnpm exec playwright test e2e/performance-audit.spec.js --project desktop` 使用真实构建和独立合成数据库执行冷/热访问、资源与 API 采样。生产采样结果见 [web-performance-2026-11-03.md（双入口实测记录）](web-performance-2026-11-03.md)。
