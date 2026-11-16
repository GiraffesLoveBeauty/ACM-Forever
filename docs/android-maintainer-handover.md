# App 修改与维护交接规范

当前为1.0.0/code45正式发布准备，基线0.2.30/code44已发布。本轮恢复管理员同包名待发布测试渠道并修正署名；PR #150第二轮本地Review通过（04f35c8），本次补录Review署名，用户已授权合并与Tag发布。线上管理员私有下载仍需运维配置与验收，不能与正式公开安装包发布混淆。具体规则见文末“1.0.0 发布交接补充”与[本轮验收](android-v1.0.0-verification.md)。自站公开镜像继续等待。

0.2.30新增的连接层维护要求继续有效：页面读取、缓存与写入分队列，GET按会话合并并限两条并发，离开取消读取而保留写事务，旧结果必须拒绝。重连只在可见页按退避策略执行；新增写入口更新关联缓存失效表。题单可选排名由后端全体筛选后分页。修改后须跑慢网切页、旧401、请求合并及草稿归属用例，不能用真实账号写生产。详见[0.2.30交付说明](android-v0.2.30-network-training.md)及[模块关联标准](android-modification-standard.md)。

0.2.29候选维护补充：每轮必须核对并同步更新日志、已核实的Review/发布署名、特别鸣谢与头像；候选未完成的操作仍留空。密码统一眼睛控件、内嵌发帖预览、本地04:00划日的检查次数、完整拼音模块编号/内容摘要及存储中的选择性模块删除都属联查项，具体执行[Android修改标准的必做同步](android-modification-standard.md#每轮修改与发布的必做同步)。手动删除的模块不再随App更新下载；原生模块须真正经系统移除split，不能仅删记录。普通缓存清理和升级仍保留已下载模块。

0.2.25 模块化评审候选：可选代码在 `Android_APP/app/advanced`、`admin`，可选资源在 `Android_APP/module-resources`。不要使用旧历史打包脚本把它们重新塞入基础 APK；发布须同时完成基础包、四个签名模块包与模块索引的回读验证。已下载模块属于持久数据，升级/清临时文件不得删除。详见[模块维护说明](android-v0.2.25-optional-modules.md)。

历史：2026-11-08曾延期1.0.0，0.2.24/code38当时沿用debug与Tag发布；记录保留在[渠道文档归档](android-v1.0.0-release-channels.md)。本轮已恢复实施，不能复用当时的code38或制品摘要。

状态：v0.2.22 随代码提请评审；记录日期 2026-11-07。适用于 `Android_APP/app/` 原生客户端。它补充[工程协作规范](TCrB-AI项目工程规范.md)及[模块关联标准](android-modification-standard.md)，不替代团队的评审、合并和发布授权。

## 维护责任与参与记录

当前 App 维护负责人为 GitHub 用户 **MiaoJJ13445**。本人确认截至 v0.2.21 的 App 历史版本均由其制作，Android 历次 PR 作者记录与之相符；目前未来数月仍由其负责。后续交接必须在 PR 中明确新负责人、范围、接手日期和待办，不能仅修改客户端显示就视为完成权限交接。

0.2.21及以前已核实的 App Review 发起者是 **Setsuna-Yukirin**，自动评审者是 **chatgpt-codex-connector[bot]**。用户于2026-11-15确认：**自0.2.22起的已完成版本由 MiaoJJ13445 本人Review**（含本地审查），对应版本据此署名；未来候选仍待实际完成后补录。公开安装包发布账号是 **github-actions[bot]**。发起评审、执行评审、GitHub人工批准、提交版本和发布制品是不同职责，不能相互替代。本人Review署名不代表GitHub人工APPROVED。GitHub 贡献者中的 `codex` 是 GitHub 提交归属账号，不能凭名字将其视为 Codex 评审机器人或某位真实成员。

人员数据入口为 `app/app/src/main/assets/releases/credits.json`；头像在 `assets/credits/avatars/`。数据只包括公开 GitHub 用户名、公开头像、职责和来源链接，不包含 QQ、密码、邮箱、Token 或管理接口返回资料。关于页与更新页共用该数据；不要各自硬编码名单。

每次新增版本：

1. 在 `people` 中登记新增参与者的准确 GitHub `login`、`kind`、`profileUrl`、公开头像来源与本地文件摘要。普通用户和机器人分别标注，头像缩为至多 96×96 PNG，单张不超过 64 KiB。
2. 在 `versions` 中增加与更新日志同名的版本；`uploaders` 表示 App 上传/提交负责人，`reviewRequesters` 表示实际发布评审请求者，`reviewers` 表示实际出具评审者，`publishers` 表示实际 Release 发布账号。
3. 从对应 PR 的评论或 review 核实人员，并保存 `evidence` 链接；本地审查可据本人明确确认补录，在 `scope` 写明确认日期和来源，不能冒充GitHub人工批准。没有发生的操作保留空数组，不预填“已评审”“已发布”。新 PR 上传前通常无法知道最终评审记录，不得为补署名伪造记录。
4. 早期 v0.1.x～v0.2.12 随 PR #48 汇总，显示该 PR 参与人时必须保留“未找到本版本独立评审记录”。v0.2.14 未公开、v0.2.16 拆分后未独立发布，不能把 Tag、草稿或本地 APK 当成公开 Release。
5. 特别鸣谢收录仓库 GitHub 贡献者和已核实的 App 评审协作者，机器人另列自动化支持。非代码贡献者取得准确 GitHub 身份后可人工补充来源；不要猜测同名账号。后继维护者及时补录新参与者，更新 `capturedOn`，不要删除历史署名。

署名是随 APK 打包的有日期快照，离线可读，不是实时 GitHub 查询。公开版本及头像变化可在下一版补录。不要仅为补录评审结果移动已公开 Tag 或替换 APK。

## 开始修改前

阅读根 README、[工程协作规范](TCrB-AI项目工程规范.md)、[Android 修改标准](android-modification-standard.md)及受影响模块文档。确认真实运行入口、最新 `main`、当前分支及工作区差异，再从共同基线创建 `codex/…` 等任务分支；版本号写入分支和 PR 标题。保留无关改动，不直接推送 `main`。

原生工程是 `Android_APP/app/`。`prototype/` 是历史浏览器预览；`AdminActivity`、`BrowserActivity`、`UpdateManager` 和 `assets/admin/` 已被 Gradle 排除。修改它们不能表示 APK 已修改。网页在 `feat/web/`，业务后端在 `feat/api/`，更改这些目录要先确认跨模块范围与上线影响。

## 修改必须同时考虑的关联

| 改动 | 同时检查 | 不可破坏的要求 |
| --- | --- | --- |
| 登录、退出、注销 | `MainActivity`、`LoginGate`、`AcmApplication`、`ApiClient`、`SessionVault`、注销流程 | 未登录只有登录界面，唯一例外为本机已有注销回执查询；无搜索、导航、设置或公共内容旁路。会话失效关闭子页和弹窗，不能返回旧缓存。自动登录验证成功前保持等待页；不能持有 API 网络锁阻塞主线程 |
| 页面入口和状态 | 页面栈、Activity 生命周期、会话代次、`ModalDialogs` | 平行栏目直接切换，子页右侧动画；防重复打开；迟到响应不覆盖新页面或新账号；敏感密码不保存到实例状态 |
| 普通读取、按钮提交 | `PageRefresh`、`ActionNotice`、`ApiClient`、相应列表 | 缓存后刷新、10 秒失败警告与持续重连；成功提示 3 秒。写失败显示错误但不能自动重放发帖、评论、绑定、审核或注销 |
| 发帖和云端草稿 | `CloudDrafts`、主编辑器、Markdown 文件归属 | 账号和草稿双代次；返回旧编辑页时同步控件；文件选择重建保留归属；防止 A 草稿覆盖 B |
| 账号和管理员 | 本人 OJ、注销、`AdminQuickActivity` 与后端鉴权 | 不使用管理 API 补公开资料；管理员入口仅 admin/root 可见，服务器最终验证权限与 CSRF；限流、认证拒绝与结果不明分开处理 |
| 题库、标签、Wiki | `ProblemTags`、题面阅读器、Wiki 目录/章节/位置 | 使用既有真实接口；标签完整匹配；站内题目链接进原生题面；返回、转屏和历史文章保留正确位置 |
| 外观、主题分享 | `AppAppearance`、`MobileStyle`、`LocalThemes`、`ThemePackage`、官方资源 | 主辅色、深浅色、透明度和间距一致；官方主题读取原资源；主题包往返完整还原、原图字节不损失；不包含账号数据 |
| 更新、版本署名、关于 | `AppUpdates`、`UpdateActivity`、`GithubCredits`、`CreditsViews`、`AboutActivity`、两份 releases JSON | 版本/签名/哈希校验不删；未登录不展示更新内容。署名不依赖业务服务器或实时 GitHub；头像和历史记录缺一项就如实提示，不假称已评审或已发布 |

完整接口及模块关联以[Android 修改标准](android-modification-standard.md)为准。客户端通过统一 API 访问数据，不能直连数据库，不把内部 Bot Token 放进安装包。缺失 API 使用“无API接口”，断网、连接失败、无权限和有效空结果分别显示；不要用虚构业务数据补位。题单与训练安排复用已经上线的真实接口，其他缺失项按修改标准的当前矩阵执行；本轮新增管理员测试分发后端，不能沿用早期“不新增后端”的历史声明。

注销回执是未登录页面的唯一例外凭据。删除回执后必须通知登录门禁，同时检查当前注销页和登录主页，不能只依赖会话失效时的检查或下一次 `onResume`；会话通知可能先于回执删除完成。此类竞态测试应固定回调顺序，不以偶然通过代替验证。

## 验证与提交

常用检查命令如下；Android SDK 35、Build Tools 35.0.0、JDK 17、Gradle 8.9 是现有构建基线。

```powershell
python -m unittest discover -s Android_APP/tests -p 'test_*release*.py' -v
python -m unittest discover -s Android_APP/tests -p 'test_theme_renderer*.py' -v
cd Android_APP/app
./gradlew --no-daemon testDebugUnitTest lintDebug assembleDebug assembleDebugAndroidTest
./gradlew --no-daemon testReleaseUnitTest testPreviewUnitTest lintRelease lintPreview :app:assembleRelease :advanced:assembleRelease :admin:assembleRelease :app:assemblePreview :advanced:assemblePreview :admin:assemblePreview
```

Windows 非 ASCII 路径可能要求 `android.overridePathCheck=true` 或使用 ASCII 构建副本；副本必须逐文件对应源码，不能用旧副本产物冒充本轮包。签名按受控环境配置，不在提交中写入本机路径或密钥。

除单元测试外，实际启动受影响 Activity，验证登录/未登录、断网、返回、重建、深浅主题、写失败与账号切换。人员与登录门禁的仪器测试模式为 `creditslogin`；注销回执恢复需跑 `accountclosure`，更新流程需跑 `startupupdates`。测试夹具仅在测试 APK 中，以 `.invalid` 保留域名阻断外网，不使用生产账号试写。

版本同步修改 `app/app/build.gradle` 的 `versionName/versionCode`、`assets/releases/history.json` 的当前版本，以及 `credits.json` 的对应条目。不要修改已经冻结的对比节点来掩盖新旧差异。记录实际运行的测试与未验证项目，不能把历史日志、机器人无意见或构建成功当成全部真机验收。

提交前只暂存任务相关文件，运行 `git diff --cached --check`，检查敏感信息、资源是否齐全及文档相对链接。源码和文档分别提交；新文档在根 README 增加入口。PR 写清范围、接口影响、测试、已知限制和未上线部分。

## Review、发布和交接

源码推送主题分支并创建 PR → 交给其他成员 review → 修复意见并重新检查当前 head → 按团队规范确认合并 → 获授权后创建新 `vX.Y.Z` Tag → Actions 编译、校验、发布 Release。机器人评审只是一项检查，不能代替另一位成员的评审或发布决定。

APK 不提交到源码 Git，不从本机代替 Actions 手工上传。相同渠道保持包名和证书不变，versionCode 必须递增；不重写已发布 Tag 或附件。发布后回下载 APK，核对真实包名、版本、摘要、签名、内置日志与更新清单，确认 latest 仅指向完整版本。v0.2.21 曾在新建草稿后的查询环节失败，保持源码和 Tag 不变重跑后成功；遇到同类错误先查日志和草稿，不能直接跳过回读或人工公开空 Release。

App Tag 发布与网页部署是两条流程。推送 `main` 且改动 `feat/**` 或服务器同步 workflow 才触发现有网页同步；不因为改了 Android 就顺带动服务器。自站镜像的独立 PR、SSH 账号、Nginx、静态目录和缓存由运维确认后单独上线，不能在未经验证的地址上切换用户下载源。

交接时移交源码 PR/Tag、签名材料保管方式、Actions 权限负责人、测试方法、接口缺失列表、未完成事项及故障恢复记录。密钥用团队认可的安全方式移交，不写入文档或聊天；交接后按实际接手情况修改维护者列表，并保留历史制作者和评审者。

## 1.0.0 发布交接补充（2026-11-16）

用户界面的开发/Review归属统一写明确GitHub用户名；不要使用“本人”。0.2.22起已完成版本由`MiaoJJ13445`执行Review，此记录不等同GitHub人工APPROVED；0.2.21及以前保留原历史。当前候选的Review不能预填；完成后据证据补为`reviewed`，下轮据Release补录发布者，禁止每个已发布包自身一直显示待Review。

新Tag由`release_credits.py`拦截未完成记录，并校对APK内快照。不得为让CI变绿而伪造人员或证据。流程与模块规则以[android-modification-standard.md（修改标准）](android-modification-standard.md)为准；1.0.0本轮本地结果见[android-v1.0.0-verification.md（正式与管理员测试验收）](android-v1.0.0-verification.md)。

测试版不是独立包：沿用当前普通版code、同签名覆盖，禁自动检查，只有管理员能手动下载；可手动返回同code普通版。公开正式更新仍走Gitee优先/GitHub回退，测试八附件仅存GitHub未公开草稿。私有代理所需服务器凭据和运维确认见[android-v1.0.0-release-channels.md（渠道与部署）](android-v1.0.0-release-channels.md)。

模块清单、归档与解包位置按code及previewTag共同定位；保留普通旧路径，不能用相同code覆盖另一渠道。恢复记录包含源code/previewTag，未来修订需对应基础包真正运行后才可作为已启用资源。离线校验记录不授权下载；显式删除须涵盖各测试修订。系统安装回执也须对应普通/测试控制器并使旧私有凭据失效。维护此链路时必跑`releasechannels`的真实系统确认/取消、`preview-resources`、`preview-resources-restart`和旧包覆盖往返，不能仅测试相同内容模块或只用adb安装替代系统回执验收。
