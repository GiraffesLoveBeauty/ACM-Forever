# Android 本人 OJ 绑定：本地接入记录（2026-11-06）

状态：源码已进入 PR #110，本记录补充评审修订，尚未合并、发布；不修改网页、业务后端或自站更新。基于 main `040bfb3ce7a55c08cbf23ac066eadb4a50cf1426`，保留既有搜索拖动修复。

## 入口与页面

- 个人中心 → 各平台通过题数：未绑定时，数字/“—”的位置显示“绑定”，直接进入该平台绑定页；已绑定时保留通过题数，零AC显示0。ALL和他人主页不显示绑定按钮。
- 账号设置 → 个人资料 → OJ账号绑定：五个平台各自一张卡。已绑定展示账号用户名和“修改”，未绑定显示“绑定”。修改进入对应平台的改绑/解绑操作页。
- CF支持申请验证码、复制验证码、本人公开资料核验、首次绑定、改绑和管理员导入账号的当前归属核验。已绑定平台还可解绑、同步及刷新状态。
- 当前服务端只有CF自助归属核验开放；其他平台保留入口并解释需联系管理员，不模拟成功，不用管理接口冒充本人绑定。

## 接口与数据约束

| 请求 | 复用契约 |
| --- | --- |
| `GET /api/me/profile` | 从 `bindings` 读取账号、`self_service`、待验证信息、来源和同步状态；`user` 的旧账号字段只作兼容展示 |
| `POST /api/me/bindings/{platform}/verification` | `{account}`，由服务器生成验证码、归属目标和有效期 |
| `POST /api/me/bindings/{platform}/confirm` | `verification_id`；已有绑定时额外带当前ACMForever登录密码、`confirmed`、`current_account` |
| `DELETE /api/me/bindings/{platform}` | 当前ACMForever登录密码、显式确认和当前平台账号；保留后端既有清理规则 |
| `POST /api/me/bindings/{platform}/sync` | 空对象，服务器决定任务排队状态；不重复触发运行中的同步 |

账号字段决定绑定状态，不能用题数是否为0或 `binding_status=pending` 推断绑定与否。没有 `bindings` 能力数据时只读旧账号字段，并显示缺少接口说明。所有写入携带既有会话Cookie/CSRF，后端最终鉴权；不收集OJ密码。归属验证请求读取超时25秒，匹配网页等待上游的时间，其余请求超时不变。

改绑或解绑前展示：该平台AC、提交证据、同步状态将被清理，进行中的挑战结束；收藏与历史学习资料保留，其他平台不受影响。当前账号归属核验保留原数据。客户端不自行清理任何数据库记录；验证失败由服务器保留原绑定。

账号/服务切换后旧页面清空，迟到结果不显示到新账号。密码、验证码和确认勾选不写入实例状态；转屏后重新向服务器获取有效验证，密码和确认需重新输入。写入期间禁止重复点击和直接返回，不自动重发写请求。成功返回后刷新个人中心及账号页，成功写入沿用共享ApiClient的缓存失效机制。

确认绑定时，将当前输入与服务器验证码记录的 `challenge.account` 直接比较，忽略账号大小写及输入首尾空白；不能与本地上次申请的 `candidate` 比较。请求构造层也执行该校验，目标不一致时不发送确认POST。用户改填新账号后，即使重新申请因本地校验或未到达服务器的网络错误失败，旧验证码也不能绑定到当前输入以外的账号；明确改回原验证码所属账号后仍可确认。

## 本地检查

首次实现阶段的127项JVM单元测试全部通过，包含11项新增绑定状态/请求校验测试；Lint无错误、57项警告，Debug主包和独立测试APK编译通过。API35真实Activity的 `ojbindings` 组已通过。后续评审验证单独记录于下文：

- 本人未绑定平台的题数位置可进入绑定页，绑定后返回刷新；已绑定但零AC显示0，隐藏绑定入口。
- 账号设置展示已绑定用户名和“修改”，可进入改绑及解绑页。
- 首次CF绑定不索取密码；改绑/解绑必须填写当前ACMForever密码并显式确认，实际请求校验CSRF及当前平台账号。
- 归属验证失败时旧账号保留；服务器待验证状态在Activity重建后恢复，密码与确认勾选不恢复。
- 已绑定账号同步、确认解绑、未开放平台提示和会话退出后的控制保护通过。

所有请求均为测试APK中的合成HTTPS响应，没有登录生产账号、修改正式绑定或联系真实OJ。已目视核对绑定列表与验证码页截图。日志：`Android_APP/dist/build-oj-bindings-final.log`、`Android_APP/dist/ui-v0221-ojbindings.log`；截图在 `Android_APP/dist/ui-v0221-screens/files/oj-bindings-{list,proof}.png`。

模拟器切换测试组时曾离线退出，重启后单独运行 `globalsearchadmin` 全组通过，日志为 `Android_APP/dist/ui-oj-search-admin.log` 和 `Android_APP/dist/ui-v0221-globalsearchadmin.log`。覆盖全局搜索、历史、零AC用户搜索、模块拖动/下拉、普通账号隐藏管理入口、服务端角色复核、CSRF/资料版本、成员改密、训练默认难度及既有GitHub更新源/自定义源隔离。测试结束已关闭专用模拟器；环境中断未记作通过。

源码与ASCII构建副本逐文件一致；主APK不包含绑定测试夹具/测试域名或历史admin资源。文档相对链接和`git diff --check`已检查；原对比节点的候选APK哈希未改变。未改后端及发布工具，因此本轮没有重跑后端或发布契约测试。

源码：`OjBindingsActivity`、`OjBindingState`、`MainActivity`、`ApiClient`、Manifest；测试：`OjBindingStateTest`、`OjBindingsUiSmoke`及`ReaderSmoke`入口。构建和测试日志位于忽略目录 `Android_APP/dist/`。

本次不发布新版本。现有 `dist/acmforever-0.2.21-debug.apk` 是上一轮拖动修复候选，尚未包含本轮OJ功能；本轮编译制品仅用于本地验收，不能把该旧候选当作本轮功能包。比较节点 [WEB-APP-20261106-01](web-app-gap-2026-11-06-v0.2.21.md) 及其JSON快照保留修改前的事实，不覆盖历史。

## PR #110 第二轮评审：验证码目标一致性

对应 review `5802150329`、[意见4493911730](https://github.com/GiraffesLoveBeauty/ACM-Forever/pull/110#discussion_r4493911730)，审查基于 `1a7ae6ba8c2427670176767ff0eb31b1bb26ff21`。已有A账号验证码时，改填B并重新申请失败会留下旧验证码；原确认逻辑比较本地 `candidate` 与输入框，可能错误地确认A。

已将确认请求构造改为接收实际输入，直接匹配验证码所属账号；本地申请校验通过后才更新候选值。增加不同账号、空值、改绑与大小写/首尾空白的契约测试，以及本地校验失败、请求未达服务器两条真实Activity回归路径。

在旧实现上运行新增界面用例，已实际复现：输入变为非法新目标后，确认请求仍把 `FirstHandle` 绑定成功，测试因目标不一致未被阻止而失败。证据为忽略目录中的 `Android_APP/dist/review110-round2-before-oj-ui.log`；测试仅使用虚构账号和合成HTTPS响应。

修复后本次实际结果：163项JVM测试全部通过，其中绑定契约13项、注销契约15项；Debug主包、独立测试APK及Lint通过，0错误、57条既有警告。API35的 `ojbindings` 整组通过，验证上述两种申请失败后确认均不发POST、原账号不误绑，明确改回验证码所属账号后可正常绑定；原有改绑、转屏清密码/勾选、同步、解绑、会话失效保护及返回刷新也通过。`accountclosure` 整组同步回归通过。

日志为 `Android_APP/dist/review110-round2-final-build.log` 与 `Android_APP/dist/review110-round2-final-ui.log`。源码与离线构建副本逐文件一致，主APK不含测试夹具或域名，冻结候选APK指纹不变。本轮未重跑其他四组界面和未改动的后端、主题、发布工具测试；更新原PR等待其他成员重新评审，不合并或发布安装包。
