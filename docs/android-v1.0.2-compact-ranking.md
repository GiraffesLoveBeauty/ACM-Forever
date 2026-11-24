# Android 1.0.2：排名小屏布局

> 范围纠正（2026-11-24）：此版本误将用户的题单计分板需求应用到普通排行榜。按用户澄清，PR #175 的 1.0.3 恢复普通排行榜旧布局，实际题单优化见 [android-xcpc-scoreboard.md（当前候选）](android-xcpc-scoreboard.md)。下文保留 1.0.2 当时的实施与发布记录，不代表当前需求范围。

日期：2026-11-24。基于 main `4e82bd5`，上一公开版本为 1.0.1/code46，本轮为 **1.0.2/code47**。源码已提交 [PR #173](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/173)，独立窗口辅助的本地代码Review未发现P0/P1/P2。用户已授权合并并先由Tag发布GitHub制品；Gitee等待用户手动同步后再发布。此处记录发布准备阶段，实际完成状态以Release和回读证据为准。

## 问题与行为

手机排名页原来在同一行放置名次、头像、昵称、身份和大号 AC 总数，长昵称与大数字争抢宽度；高装饰横幅及长筛选按钮也占用了较多首屏空间。

本轮改为：

- 顶部使用“排名”短标题及 44dp 图标筛选入口，搜索时保留关键词提示。筛选窗口仍提供平台组合、排序及每页数量。
- 日期选项为 11sp、左右内边距 9dp，保留 44dp 触摸高度；空间不足时自动换行。
- 成员卡片水平内边距为 12dp、垂直内边距为 10dp，卡片间距为 8dp。
- 第一层展示名次、32dp 头像和昵称/身份；名次按内容占宽，昵称为 14sp，身份为 10sp，长文字单行省略。
- 第二层展示 13sp 总 AC 和 11sp 平台统计，使用按内容换行的布局，移除右侧大号总数。
- 平台摘要使用 CF、AT 等短称；平台明细、筛选名称和接口字段保持明确。

现有排序、日期和平台筛选、零 AC 过滤、分页、下拉刷新和公开成员主页仍复用原逻辑与接口。通用横幅、论坛、题库及个人中心布局不随本轮排名收缩。

## 版本与维护记录

- `build.gradle`、`history.json`、`credits.json` 同步为 1.0.2/code47。
- 本轮按真实本地报告补为 `reviewed`，Review发起者/Review者为MiaoJJ13445，审查提交`a91a24b13bc2cc1afcc6ba683666f8c9b478b4f8`。发布者在公开完成前保持空数组；发布门禁仍校验署名与APK内快照一致。
- 按实际公开 Release 补录 1.0.0、1.0.1 的 `github-actions[bot]` 发布记录，保留原开发与 Review 来源。
- 2026-11-24重新核对9名公开代码贡献者，均已在特别鸣谢收录；现有离线头像摘要继续校验。

功能拆分、小组件、提醒等产品讨论不属于本轮实现范围。网站、业务 API、更新源、四个可选模块及发布工作流未修改。

## 验证

2026-11-22 本地基线验证：debug APK 与 instrumentation APK 构建成功；既有 JVM 测试 253 项通过、3 项跳过，0 失败；Lint 0 错误、70 条警告。此记录仅说明当时执行范围。

2026-11-24 同步主线并保留搜索提示后：

- 发布/署名/Gitee恢复、独立模块编号和官方主题资源检查合计 **103项通过，无失败或跳过**。
- 版本号/code、当前日志、人员快照、离线头像摘要及文档相对链接校验通过；`git diff --check`通过。
- 本轮本机 Android 构建在依赖解析阶段停止：SDK 35缓存缺少`build.prop`等关键文件，Gradle报告`Failed to find target with hash string 'android-35'`。既有解压缓存也不完整，未伪造SDK文件或降低编译标准。该轮没有执行到JVM测试、Lint或APK编译，不能沿用11月22日的通过结果作为当前版本通过。
- 本地尝试启动隔离的无窗口模拟器，但未获得可用实例，因此没有执行本轮仪器测试。真机/鸿蒙、320dp小屏及系统大字体仍待验收。
- 已取得原失败日志：Maven Central下载构建依赖时返回HTTP 429，尚未进入App编译；对同一提交重跑后，[Android CI](https://github.com/GiraffesLoveBeauty/ACM-Forever/actions/runs/45374745465/job/138386873090)于2026-11-24 18:44:25（Asia/Shanghai）成功，三渠道JVM/Lint/构建步骤通过。
- 发布前只补录署名、日志与本文证据，不修改运行时代码；补录差异需再次核对，最终head仍须通过Android CI后才合并。

## 本轮发布顺序

1. GitHub Actions变量`GITEE_MIRROR_MODE`设为`manual`并回读确认，保留App的Gitee优先/GitHub回退设置。
2. PR最终head通过CI后按用户授权合并；创建新的不可变`v1.0.2`Tag，由现有Action构建、签名及发布GitHub八附件。
3. 回读校验主APK、校验文件、两份JSON和四个模块，确认版本/code、大小、哈希、签名及内置记录。
4. Gitee本轮不自动发布，等用户手动同步源仓库后再继续同版镜像；不提前操作其Release或附件。

维护关联：[android-modification-standard.md（模块关联与修改标准）](android-modification-standard.md)、[android-maintainer-handover.md（维护交接规范）](android-maintainer-handover.md)。
