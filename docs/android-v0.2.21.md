# Android v0.2.21：搜索拖动修复与成员功能适配

状态：2026-11-06，`0.2.21` / versionCode `35` 待评审提交。提交前核对远端 main 仍为 `040bfb3ce7a55c08cbf23ac066eadb4a50cf1426`，与本地基线一致；已发布版为 `v0.2.20` / code `34`。按用户最新指示，将当前已完成源码提交新PR并等待其他成员review；本轮不合并、不创建Tag或发布Release。自站PR #105与服务器配置继续等待管理员。

## 本次PR完整范围与最终验证

- 修复搜索设置模块向上拖动越界及边缘自动滚动过快，保留纵向跟手、90%缩放、松手保存与取消恢复。
- 本人OJ绑定入口、归属核验、改绑、解绑与同步，按现有服务端能力显示；详情见[OJ绑定实施记录](android-oj-bindings-local-2026-11-06.md)。
- 账户注销入口、实时服务器开关、管理员交接限制、本人密码确认及加密回执恢复；结果不明时只查询，不重复提交，见[账户注销实施记录](android-account-closure-local-2026-11-06.md)。
- 题库、比赛进度及对应全局搜索模块支持原始标签精确筛选、真实候选搜索和关键词组合，见[标签筛选实施记录](android-problem-tags-local-2026-11-06.md)。
- Wiki完整分类、路径、标签、章节跳转/高亮及返回/转屏阅读位置恢复，见[Wiki导航实施记录](android-wiki-navigation-local-2026-11-06.md)。

最终源码的157项JVM测试全部通过；Debug主包与独立测试APK编译成功；Lint 0错误、57条既有警告。API35原生模拟器的`wikinavigation`、`web`、`problemtags`、`globalsearchadmin`、`ojbindings`、`accountclosure`六组全部通过。发布契约38项、官方主题资源2项测试通过。

提交前检查命令与本地证据：

- Gradle：`:app:testDebugUnitTest :app:assembleDebug :app:assembleDebugAndroidTest :app:lintDebug`；`Android_APP/dist/build-wiki-navigation-final.log`。
- Wiki/共享阅读器/标签/搜索界面：`Android_APP/dist/ui-wiki-navigation-regression.log`。
- 对最终构建补跑OJ/注销界面：`Android_APP/dist/ui-pr-v0221-account-regression.log`。
- Python：`python -m unittest discover -s Android_APP/tests -p 'test_*release*.py' -v`和`python -m unittest discover -s Android_APP/tests -p 'test_theme_renderer*.py' -v`；各38项和2项通过，日志为`Android_APP/dist/pr-v0221-{release,theme}-tests.log`。
- 逐文件确认源码与构建副本一致，主APK没有测试域名/夹具；Markdown链接与差异空白检查通过。上述构建、日志、截图、签名不提交源码Git。

所有界面测试使用合成HTTPS响应与虚构账号，没有执行生产绑定、注销或其他生产写入。未修改`feat/`、业务数据库、工作流、自站或发布工具；未加入题面AI翻译、中文标签组合筛选、批量开户等重管理。源码PR不会创建版本Tag或发布APK，实际生产与真机验收仍需另行完成。

以下保留最初拖动修复的116项测试与旧候选APK记录。它们不是本次完整源码的最终制品；固定比较节点`WEB-APP-20261106-01`和原候选哈希未改写。

## 问题与修复

1. **模块向上拖动覆盖操作区。** 原动画只限制选中模块，邻居在提前让位时可被推到列表外。已将所有行的目标和实际位置限制在列表内部，触界清零速度，并开启容器裁剪。相同复现用例中，首行 Y 坐标从修复前 `-3.0px` 变为 `0.0px`。
2. **边缘自动滚动太快。** 原逻辑每帧移动 9dp，60Hz 下约 540dp/秒、120Hz 下约 1080dp/秒。现改为按实际时间及屏幕密度计算，最高 96dp/秒，越靠近边缘越快，约 120ms 平滑加速。离开边缘立即停止，反向清旧速度，卡顿单帧最多计 50ms；小窗口保留中间停止区。
3. **限位后仍能进入首尾位置。** 不同高度的卡片即使已到边缘，其中心也可能无法越过邻居中心。到达列表顶部或底部时允许进入对应首尾槽位，避免卡片被夹住或叠在首行。

保留长按后全体 90% 缩放、仅纵向跟手、逐行提前让位、松手保存、取消恢复和无障碍上下移动。该实现为动画模型，快速拖动的中间帧不保证刚体式零重叠；所有卡片始终受列表边界限制。

## 修改关联

- `ModuleDragPhysics`：统一列表上下限、首尾位置和邻居弹簧边界。
- `ModuleEdgeScroll`：可单测的按时间滚动，积分加速并保留小数像素，减少刷新率差异。
- `ModuleOrderView`：接入滚动模型、列表裁剪和长按开始/结束的速度清理。
- JVM 与独立测试 APK：边界、不同高度、快速反向、帧率、停止和实际指针滚动回归。
- `build.gradle` / `assets/releases/history.json`：版本与内置更新说明同步为 0.2.21 / 35。

网站和共享后端的新功能只读核对见 [web-updates-since-android-v0.2.20.md](web-updates-since-android-v0.2.20.md)，本轮不修改 `feat/**`、发布工具、工作流或自站源。

## 本地验证

JDK 17、Gradle 8.9、Android SDK 35 离线构建。`testDebugUnitTest`、`assembleDebug`、`assembleDebugAndroidTest`、`lintDebug` 通过；Lint 无错误、57 项警告。116 项 JVM 测试无失败和错误，其中新增首尾限位、不同高度、快速反向、60/120Hz 同时间距离、渐变速度上限、离边停止、反向、小窗口及卡顿帧回归。

API35 模拟器的 `globalsearchadmin` 最终回归通过：

- 真实指针长按后全体缩至90%，向上拖动不越过列表顶部，首尾卡片与不同行高的限位保持合法；到顶部可交换首项，取消恢复原序。
- 全部模块启用后，上下边缘分别保持900ms，实际滚动方向正确、距离不超过按经过时间计算的慢速上限，手指回到中间后滚动停止。
- 原搜索历史、热搜、单列结果、独立失败、上下文恢复、普通账号不显示管理入口、服务端角色重验证、CSRF、资料版本、改密与训练默认值回归通过。
- 实际软键盘聚焦与点击唤起、既有GitHub更新源及自定义源隔离继续通过。

日志 `Android_APP/dist/ui-v0221-globalsearchadmin.log`，截图 `Android_APP/dist/ui-v0221-screens/files/search-drag-top-bounds-v0221.png`，已目视核对卡片没有覆盖上方操作区。测试使用独立测试 APK 与合成 HTTPS 数据，不读取或写入真实成员及生产数据；不等同厂商系统真机验收。本轮未修改后端或发布工具，未重复运行后端和发布契约测试。

## 本地安装包

候选文件：`Android_APP/dist/acmforever-0.2.21-debug.apk`，大小 **3,334,544 字节**，附同名 `.sha256`。包名 `com.giraffeslovebeauty.acmforever`、versionName `0.2.21`、versionCode `35`、minSdk `26`、targetSdk `35`；实际 APK 与源码版本及35版内置日志一致。

SHA-256：

```text
68912db326337b0657c840cc5115ee0fc7370680cbaedfe48cb0f0936334df47
```

APK 签名校验通过，固定调试证书 SHA-256 为 `88c9f163cbf379aeca7bc110f66c542a838d0d8e3970f24fd96582bec8e93fe4`，与已发布 v0.2.20 相同。同包名同渠道支持覆盖安装；安装失败时仍应核对设备实际错误，不需要默认清除账号及主题数据。

打包前逐文件核对本地 ASCII 构建副本与当前源码一致，主 APK 不含测试夹具或历史 admin 资源；核验报告位于忽略目录 `Android_APP/app/app/build/qa-v0221/package-verification.json`。安装包、截图、日志、密钥和缓存不提交 Git；本地候选不等于 Actions 已发布制品，GitHub最新公开版仍为 v0.2.20。
