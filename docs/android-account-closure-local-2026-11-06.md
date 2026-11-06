# Android 本人账户注销（2026-11-06，仅本地）

状态：v0.2.21/code35 源码已进入 PR #110，本记录补充评审修订；尚未合并、发布。本轮仅接入仓库已有接口，不修改网页、后端、服务器开关、自站或发布链。旧 `dist/acmforever-0.2.21-debug.apk` 未重打包，不能用它验收此功能。此前网页/App 对比节点保留当时结论，不覆盖。

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

**已明确拒绝的提交不进入结果恢复。** 现有后端在注销提交事务前可能返回 `429` 且 `code=RATE_LIMITED`。仅该状态码与业务码同时匹配时，将本次提交视为未执行，清除事先保存的待确认回执，保留登录态，并提示“注销请求过于频繁，本次未执行注销。请稍后重新检查。”用户可手动“重新检查”取得新预览；不会自动再次提交，也不保存密码。回执查询本身返回同样限流时仍属结果不明，必须保留原回执继续查询；无业务码的429、未知业务码、超时和5xx也不能据此清除恢复信息。

注销POST明确返回 `401 / AUTH_REQUIRED` 同样发生于提交事务前：清除待确认回执，提示“登录已失效，本次未执行注销。请返回重新登录后重新检查。”按已有ApiClient规则清除过期会话，用户重新登录后可手动取得新预览，不自动提交。只对状态码与业务码同时匹配的明确响应应用此规则；裸401、未知认证码或回执GET的401仍保留原回执与结果未确认状态。匿名回执请求不会因为查询失败而清理其他正常登录会话。

## 本地验收

见本轮实际构建日志 `Android_APP/dist/build-account-closure-final.log` 和模拟器测试模式 `accountclosure`；`dist/` 和测试输出均忽略，不进入源码Git。单元测试覆盖请求字段、本人密码、过期、管理员预览、规则版本、来源/令牌格式、回执匹配、真正提交时间与网络结果分类。模拟器全部使用合成HTTPS响应和虚构账号，拒绝外部流量，未注销任何生产账号。

界面验收范围：入口顺序、开关关闭不提交、两个等大按钮/红色50%透明、猫娘、取消、admin/root及角色临时变化、密码错误、转屏清密码/不重发、成功立即清凭据、返回原登录页、POST响应丢失后回执恢复、pending不冒充成功、加密回执重建和同QQ新代账号保护。

2026-11-06 首次实现阶段的实际结果（后续评审验证见下一节）：

- `:app:testDebugUnitTest`：138项、0失败（本轮注销契约11项）。
- `:app:assembleDebug`、`:app:assembleDebugAndroidTest`：通过；源码与离线ASCII构建副本逐文件一致。
- `:app:lintDebug`：0错误、57条既有警告，本轮未增加警告。
- 独立API35模拟器的 `accountclosure` 整组通过，上述注销边界均以真实Activity配合合成HTTPS响应验证。确认/成功窗口的软件截图已目检，位于忽略目录 `Android_APP/dist/ui-account-closure-screens/closure-confirm.png` 与 `closure-success.png`。
- 同一最终构建的 `ojbindings`、`globalsearchadmin` 回归整组通过。日志分别为 `Android_APP/dist/ui-closure-device-accountclosure.log`、`ui-closure-device-ojbindings.log`、`ui-closure-device-globalsearchadmin.log`。
- 最初参考模拟器多次意外离线，相关尝试中断，未计作通过；随后建立独立测试AVD完成上述验证，原AVD数据未清除。
- Markdown相对链接有效，`git diff --check`通过；主APK不含测试域名/夹具和历史admin资源；冻结对比节点里的原候选APK哈希不变。网页、业务后端与工作流没有本轮差异。

上述首次本地验收未执行任何生产注销、上传、PR或Tag操作。随后源码进入 PR #110；编译制品只留在本机临时构建目录，未替换旧 `dist/` 候选。以上不是正式服务器验收。

## PR #110 评审修订：提交限流恢复

对应 review `5801811996`、[意见4493664999](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/110#discussion_r4493664999)，审查基于 `4ae6f9f9851c42e02d50c28f703606c59f2af20c`。问题是提交被明确限流后，客户端仍保存回执并进入持续等待，转屏或重开页面也无法重新预览。

修订仅涉及客户端错误分类、提示、回归测试及内置更新说明。已核对 `feat/api/acm_api/account_closure_api.py`：提交的 `submit` 与 `reauth` 限流发生于注销事务前，回执GET则另有限流。两条路径不能共用清理待确认回执的行为。

本次实际验证：

- 先将新增测试应用到旧实现，159项中 `explicitSubmitRateLimitIsPreCommitRefusal` 失败，复现原问题；证据为忽略目录中的 `Android_APP/dist/review110-rate-limit-before.log`。
- 修复后 `:app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug` 全部通过。JVM共159项，0失败/错误/跳过；其中注销契约13项。Lint为0错误、57条既有警告。日志 `Android_APP/dist/review110-rate-limit-final-build.log`。
- 独立API35模拟器的 `accountclosure` 整组通过：提交限流清除加密回执，保持登录、不查询回执也不重复POST；转屏仍显示明确拒绝，手动重新检查生成新请求编号且密码为空；模拟进程级控制器重建后不恢复无效回执。
- 同组回归验证回执GET限流继续保留原加密回执和未确认状态；原有管理员限制、密码错误、成功清理、响应丢失恢复及同QQ新代账号保护通过。日志 `Android_APP/dist/review110-rate-limit-ui.log`。仅使用虚构账号和合成HTTPS接口，未执行生产注销。
- 本次只重跑受影响的注销界面组，其他五组界面的既有结果见 [v0.2.21实施记录](android-v0.2.21.md)，不能视为本次重新运行。源码与构建副本一致，主APK无测试夹具，冻结候选APK指纹不变。

此修订更新原 PR #110，等待其他成员重新评审；不合并、不创建Tag、不发布APK。

## PR #110 第二轮评审：提交认证失败恢复

对应 review `5802150329`、[意见4493911745](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/110#discussion_r4493911745)，审查基于 `1a7ae6ba8c2427670176767ff0eb31b1bb26ff21`。会话在提交前刷新成功、注销POST实际处理前失效时，后端 `current_identity()` 会明确拒绝，本次并未启动注销事务。原客户端却保存回执并进入持续查询。

修订新增严格的 `401 / AUTH_REQUIRED` 分类及重新登录提示，复用现有明确拒绝后的回执清理路径，不更改回执查询逻辑。先在旧实现添加测试，161项中 `explicitSubmitAuthenticationFailureIsPreCommitRefusal` 失败，已复现遗漏；证据为忽略目录中的 `Android_APP/dist/review110-round2-before-build.log`。裸401、未知认证码及503携带同名业务码仍要求查询回执。

本次修复后实际验证：

- `:app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug` 全部通过。163项JVM测试无失败/错误/跳过，其中注销契约15项，绑定契约13项；Lint 0错误、57条既有警告。日志 `Android_APP/dist/review110-round2-final-build.log`。
- API35的 `accountclosure` 整组通过。合成接口在提交前会话刷新成功、POST处理时返回401认证拒绝；客户端清空加密待确认回执、保留“未执行”提示，既不查询回执也不再次POST。转屏不恢复无效回执；重新登录后手动检查取得新预览、密码为空，进程级控制器重建后也可重新预览。
- 回执GET返回401认证失败时，继续保留原加密回执和未确认状态，正常登录会话不受影响；原有限流恢复、错误密码、管理员限制、响应丢失、成功清理及同QQ新代账号保护通过。同期 `ojbindings` 整组也通过。日志 `Android_APP/dist/review110-round2-final-ui.log`。
- 只重跑受影响的两组界面，不将其他四组和发布/主题的旧结果写成本次新验证。源码与构建副本一致，主APK无夹具，冻结候选APK未替换；没有执行生产请求或修改后端。

本次更新原PR等待重新评审，不合并、不创建Tag、不发布APK。
