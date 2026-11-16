# Android 1.0.0 本地检查与发布条件

检查日期：2026-11-16。基线：已发布0.2.30/code44，main `672427d94ce824fdeeb80ac9b0df039928dcc149`。本轮为1.0.0/code45正式候选，恢复管理员手动待发布测试渠道。**本地候选未完成外部Review，未发布、未部署，不是已上线1.0.0。**

## 本轮发现与修正

1. 关于页把维护者描述为“本人”，阅读者会误解归属。现改为明确GitHub用户名`MiaoJJ13445`；版本范围与关于页共用同一离线记录。
2. 已发布0.2.29和0.2.30的APK仍将自身Review记录留在开发状态。源码已按PR #144/#145及用户确认补正已完成历史；0.2.22起实际Review署名`MiaoJJ13445`，早期人员保留，不把机器人无意见当作GitHub人工APPROVED。已发布附件不覆盖，修正在1.0.0及后续包中体现。
3. 原测试允许每个“当前版本”永久空Review，不能防止再次发布错误快照。新增`reviewed`状态和`release_credits.py`：实际Review完成后补PR/证据/人员，Tag校验、APK清单和正式/测试发布均验收；APK快照必须与源码相同。本轮仍为development/空Review，正式发布门禁会按预期拒绝。
4. 恢复旧双渠道实现时补上当前四模块机制：测试基础包及四模块都走管理员会话代理，签名/大小/hash/安装版本一致；不把草稿附件URL作为公共下载。保留当前模块健康恢复、独立revision、Gitee回退、04:00日检查、弱网请求调度和草稿归属保护。
5. 补正旧仪器测试：练习→进入题库、比赛进度独立题目卡、Gitee回退与手动检查；Activity重建使用新实例生命周期事件，避免把返回页resume当作重建完成。没有为适配旧测试而改回旧界面。

修改标准与交接要求已同步，见[android-modification-standard.md（维护规则）](android-modification-standard.md)、[android-maintainer-handover.md（交接）](android-maintainer-handover.md)。

## 已执行的验证

| 检查 | 实际结果 |
| --- | --- |
| Python发布/模块/主题/API适配 | 112项通过，含既有头像PNG尺寸/hash与历史证据校验，以及新的署名门禁和正式/私有八附件事务 |
| 后端完整回归 | 485项，无失败，1项跳过；最后小型权限修订另重跑管理员测试分发14项，全部通过 |
| JVM基础包 | debug/release/preview各250项，无失败，各2项因Windows符号链接环境跳过；Linux CI仍执行对应断言 |
| JVM便捷管理 | release/preview单测通过 |
| Android Lint | 三变体各0 errors、71 warnings；包括现有绘制分配、中文文本资源化、无障碍等提醒，未称已清零 |
| 实际构建 | 正式与preview.1/preview.2、两个原生split及仪器测试包成功；固定证书一致，两种新分发均debuggable=false |
| 制品 | 每种候选各八附件，SDK包名/code/渠道/真实清单验证，资源包JAR签名和原生split签名/metadata验证通过；候选清单明确标记本地验收，不能拿它发布 |
| 离线鸣谢 | 2026-11-16只读查询公开贡献者，9个贡献者均已收录；保留12个已知人员/机器人及本地头像，不添加虚构参与者 |
| 工作区保护 | 外层延期工作区36个文件的SHA256均未变化；实际构建副本256个src文件与本任务源码一致 |

模拟器为Android15/API35，运行真实正式APK、真实Activity与签名模块；业务HTTP由测试包完全拦截，使用假账号/数据，不写生产。已通过：强制登录及本机注销回执例外、关于/历史署名、每日自动检查/最新确认/下载取消、Gitee回退、缓存与恢复、弱网切页/并发读取/304/no-store/迟到401、草稿切换及提交/图片归属、论坛增量分页、题单排名及读取、OJ绑定、注销恢复、Wiki导航、题目标签/题面字体、私人主题往返/分享/位置恢复、官方模板布局与交互、全局搜索排序及管理员权限、页面栈与阅读位置。

升级与私有下载往返已完成，结果见下节；不能由本地拦截网络验收推定生产下载已通。

## 制品与迁移结果

本地候选目录：`Android_APP/dist/local-v100-20261116/`（忽略于Git）。它们仍含待Review状态；发布必须在实际Review和补录完成后由Tag Action重建，不能手动上传本地候选冒充已评审制品。

| 基础包 | 安装code | 大小/摘要 |
| --- | --- | --- |
| release/acmforever-1.0.0.apk | 45 | 1,004,553字节，SHA256 `d6fbf12336aa239acddda7412a7eca651c26c658b3c79d750cb5396c4b57b3b4` |
| preview.1/acmforever-1.0.0-preview.1.apk | 44 | 1,004,539字节，SHA256 `d412800c06926360042ba53d788bc12c89e5a1cf10e6d694b9761ab2dea6f175` |
| preview.2/acmforever-1.0.0-preview.2.apk | 44 | 1,004,550字节，SHA256 `c95c7766880370a2e2c103360951a589a77a0bb00a42e1bb2e4ec438f7835e05` |

Android 15/API 35 隔离模拟器最终迁移验收：

- 使用从公开 Release 回下载的真实 0.2.30/code44 APK 及四模块，确认旧客户端可读取真实 1.0.0 正式候选清单并发现升级。
- 连续覆盖 `0.2.30 → 1.0.0-preview.1 → 0.2.30 → 1.0.0-preview.1 → 1.0.0`，该往返期间没有卸载、清数据；每一步均校验账号、Keystore 加密密码、主题及透明度、搜索历史、私有文件和四个模块完整性。
- 在测试版中，将已保存的自动更新选项设为开启仍不会发自动检查请求；手动可发现并校验同 code 的普通版切回包。
- 独立场景验证 `preview.1` 选择真实 `preview.2`：普通成员被拒，管理员主包及四模块通过同源 Cookie 代理下载，没有匿名回退；校验真实 APK/模块的签名、包名、版本、修订、大小和 SHA256，验证模块取消、安装 Provider 只读、退出后文件授权失效和有效空结果。
- 修正验收夹具首次初始化漏建下载目录的问题；修正仅在仪器测试中，不改变业务模块目录规则。上述为修正后实际通过结果。

## 真实网络与发布前待办

本机通过当前代理匿名只读观察：Gitee `releases/latest`返回404；GitHub公开update.json返回200，为0.2.30/code44/debug；业务capabilities返回200；新增私有测试接口返回404。此结果不代表所有手机/网络情况，不含管理员登录或真实草稿下载验证。

发布前仍须完成：

1. 交当前最终head给用户安排的Review；实际通过后补录1.0.0人员、PR与证据，复核差异，确认发布门禁通过。
2. 运维确认合并部署及配置`ACM_ANDROID_GITHUB_TOKEN`。本轮`feat/**`合并会触发既有服务器同步；没有Token时仅私有测试渠道503，不能宣称验收上线完成。无数据库迁移。
3. 经授权创建测试Tag，由Action生成私有八附件并回读；管理员手机登录后验证下载/取消/权限失效、模块安装、切回普通版。源配置与草稿权限不能由本机假传输测试替代。
4. 手机真机确认0.2.30→测试→普通版→1.0.0升级及数据保留，系统安装确认由用户操作；本轮没有苹果/iOS或鸿蒙全量验收。
5. 授权后创建正式Tag，由Action发布正式八附件；维护者手动镜像到Gitee并确认latest返回200及附件一致，不能只同步Git源码。自站公开镜像仍等待，不属于本次私有代理。

渠道、部署、退役与回退细节见[android-v1.0.0-release-channels.md（正式与待发布测试版）](android-v1.0.0-release-channels.md)。

## 本地日志位置

`Android_APP/dist/`下的`build-v100-fourth.log`、`build-v100-preview2-final.log`、`build-v100-instrument-final.log`、`build-v100-migration-tests.log`、`migration-v100-setup-final.log`、`migration-v100-roundtrip-final.log`、`migration-v100-private-final.log`、`tests-v100-python-all.log`、`tests-v100-api-all.log`、`tests-v100-backend-final.log`与`validation-v100/`记录实际执行。APK、模块和含本机路径的日志不提交源码仓库；PR仅带源码、测试及本说明。
