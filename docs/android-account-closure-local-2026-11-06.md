# Android 本人账户注销（2026-11-06，仅本地）

状态：本地 v0.2.21/code35 后续源码，未提交、未上传 PR、未发布。本轮仅接入仓库已有接口，不修改网页、后端、服务器开关、自站或发布链。旧 `dist/acmforever-0.2.21-debug.apk` 未重打包，不能用它验收此功能。此前网页/App 对比节点保留当时结论，不覆盖。

## 用户流程

账号设置的“退出登录”下新增“账户注销”。每次进入实时读取 `GET /api/auth/me`，不开缓存；`account_closure_enabled=false` 或接口明确 `FEATURE_DISABLED` 时提示“注销窗口关闭”。源码默认开关关闭不能代表生产实际状态，App 不修改该开关。

开启后读取注销预览，显示“真的要注销吗？”、删除与保留后果、沿用现有分层角色绘制的哭泣猫娘和两个等大按钮：50%透明红色“狠心注销”、主题色“点错了喵”。后果采用服务端 `retention_notice.text`：私有刷题/训练记录、源码、收藏、草稿和绑定删除；已发布话题、评论、Wiki 历史及公共引用图片保留并匿名；保留最小墓碑、必要受限引用、180天审计及最长30天备份，不删除外部OJ账号，也不退出QQ群。具体以服务端当前规则为准。

点击“狠心注销”重新验证登录身份、注销开关与账号代次。admin/root 提示“管理员无法执行注销，需要先交接权限、降为普通成员”，不发注销POST。普通成员仍须填写**本次 ACMForever 登录密码**；这是后端既有强制要求，不是OJ密码。密码错误不退出账号、不显示成功；密码、CSRF、回执令牌均不进实例状态或日志。

只有提交或回执返回匹配的请求编号、规则版本、`status=closed` 和有效提交时间，才显示“感谢你的陪伴，我们会加油的，祝你天天开心”及“注销成功”。此时立即清理原账号会话、缓存、保存密码、自动登录、提醒和草稿内存，保留本机主题/背景。“返回登陆界面”只负责回到原账号页的登录表单，不再次提交注销；迟到的旧回执不得退出同QQ新代账号或清掉其草稿。

## 接口与关联

| 操作 | 现有接口 | 约束 |
| --- | --- | --- |
| 登录/开关 | `GET /api/auth/me` | 实时、仅后台线程，校验会话代次 |
| 后果预览 | `GET /api/me/account-closure/preview` | 无缓存，当前只接受 `closure-v2`；缺少完整保留规则时不开放提交 |
| 确认注销 | `POST /api/me/account-closure` | CSRF + `Idempotency-Key` + `X-Closure-Receipt`；body只有当前密码、`confirm_text=注销账号`、规则版本、预期账号代次 |
| 查询回执 | `GET /api/account-closures/{request_id}` | 仅 `X-Closure-Receipt`，不附Cookie/CSRF，不接收或改写普通会话 |

`AccountClosure` 严格解析预览/回执；`AccountClosureFlow` 由 Application 持有，Activity重建仅重新订阅，不重放POST。`SessionVault` 在提交前将回执与来源、账号、代次使用独立AAD加密落盘，保存失败则不提交。`AccountClosureActivity` 承担窗口和返回流程；`ApiClient` 承担当前身份约束及原账号失效处理。注销页非导出，普通退出登录逻辑不变。

## 结果不明与恢复

超时、断网、服务器异常或401均不能证明成功。发生结果不明时只查回执，显示真实“尚未确认”状态；页面可见时每5秒查询，离开即停止轮询，再次进入继续。转屏与进程内重建不重复提交；进程重启后再次进入注销页可用加密回执恢复查询。即使服务端开关随后关闭，已保存回执仍可独立查询。密码不会落盘。

回执过期或无效时提示结果无法确认，联系管理员或到网页端核对，不自动新建注销请求。若进程恰在回执保存后、POST送达前退出，也按未确认处理；此边界不以重复POST冒险。已确认成功但尚未按返回按钮时，回执保留用于恢复告别页面，确认返回后删除。

## 本地验收

见本轮实际构建日志 `Android_APP/dist/build-account-closure-final.log` 和模拟器测试模式 `accountclosure`；`dist/` 和测试输出均忽略，不进入源码Git。单元测试覆盖请求字段、本人密码、过期、管理员预览、规则版本、来源/令牌格式、回执匹配、真正提交时间与网络结果分类。模拟器全部使用合成HTTPS响应和虚构账号，拒绝外部流量，未注销任何生产账号。

界面验收范围：入口顺序、开关关闭不提交、两个等大按钮/红色50%透明、猫娘、取消、admin/root及角色临时变化、密码错误、转屏清密码/不重发、成功立即清凭据、返回原登录页、POST响应丢失后回执恢复、pending不冒充成功、加密回执重建和同QQ新代账号保护。

2026-11-06 实际结果：

- `:app:testDebugUnitTest`：138项、0失败（本轮注销契约11项）。
- `:app:assembleDebug`、`:app:assembleDebugAndroidTest`：通过；源码与离线ASCII构建副本逐文件一致。
- `:app:lintDebug`：0错误、57条既有警告，本轮未增加警告。
- 独立API35模拟器的 `accountclosure` 整组通过，上述注销边界均以真实Activity配合合成HTTPS响应验证。确认/成功窗口的软件截图已目检，位于忽略目录 `Android_APP/dist/ui-account-closure-screens/closure-confirm.png` 与 `closure-success.png`。
- 同一最终构建的 `ojbindings`、`globalsearchadmin` 回归整组通过。日志分别为 `Android_APP/dist/ui-closure-device-accountclosure.log`、`ui-closure-device-ojbindings.log`、`ui-closure-device-globalsearchadmin.log`。
- 最初参考模拟器多次意外离线，相关尝试中断，未计作通过；随后建立独立测试AVD完成上述验证，原AVD数据未清除。
- Markdown相对链接有效，`git diff --check`通过；主APK不含测试域名/夹具和历史admin资源；冻结对比节点里的原候选APK哈希不变。网页、业务后端与工作流没有本轮差异。

以上不是正式服务器验收，也未执行任何生产注销、上传、PR或Tag操作。最新编译制品只留在本机临时构建目录，未替换旧 `dist/` 候选。
