# Android Wiki 完整目录与阅读导航（2026-11-06，仅本地）

状态：v0.2.21/code35 后续本地源码，待跨人评审。仅复用已有公开Wiki接口，不修改网页、业务后端、数据库、自站或发布工作流，不提交、推送或发布APK。旧 `Android_APP/dist/acmforever-0.2.21-debug.apk` 未替换，功能比较节点 `WEB-APP-20261106-01` 保留原核对结论。

## 页面与交互

- Wiki首页按服务器顺序展示知识大类、下级分类、已发布文章数和分类描述；分类下可看文章，全站文章另有入口。
- 分类页显示可点击的分类路径、下级分类和公开文章，列表保留搜索与分页；文章列表展示接口提供的分类名称、摘要和标签。
- 正文展示分类路径和条目标签；路径可返回对应分类，知识目录可返回完整目录页。公开历史、当前版本、来源/许可和关联练习继续保留。
- 阅读正文时，在页面上方保留“当前章节”和“文章目录”。目录从经过清理和公式排版的实际正文标题生成，涵盖一至六级标题，按层级缩进，主题色标记当前章节；点击直接滚动外层阅读页面，正文滚动同步更新当前章节。
- 重复标题使用不同锚点，代码块中的`#`不会被误当标题；没有标题时明确显示“本文暂无章节目录”。历史版本使用该版本自己的标题，显示历史标记并提供“阅读当前版本”。
- 当前章节及章内偏移保存在当前页面状态，目录/分类/公开历史返回和Activity重建时恢复；离开后返回原生关联题面也继续保留原阅读页。这里只保存页面导航状态，不建立云端阅读记录。

## 现有接口与数据来源

| 用途 | 公开接口 | 使用字段 |
| --- | --- | --- |
| 完整分类目录 | `GET /api/wiki/navigation` | `categories`、`parent_id`、`published_count`；未提供文章数时不编造数字 |
| 分类路径与下级分类 | `GET /api/wiki/categories/{id}` | `category`、`path`、`children` |
| 分类/全部文章 | `GET /api/wiki/pages` | 可选`category_id`、`page`、`page_size=20`；无分类时不发送非法的0 |
| 文章搜索 | `GET /api/wiki/search` | `q`、分页；与原全局Wiki搜索使用同一公开来源 |
| 当前/历史正文 | `GET /api/wiki/pages/{slug}`、`…/revisions/{id}` | `body`、`path`、`tags`、摘要、来源、许可与关联练习 |
| 公开历史 | `GET /api/wiki/pages/{slug}/revisions` | 版本编号、标题与发布时间 |

匿名也可阅读公开内容。目录、分类说明与文章结果独立读取，目录故障不会阻塞按slug直接阅读文章，分类信息失败也不会吞掉已经读到的列表。沿用真实缓存、10秒连接预警、持续只读重试及错误/空结果区分。

## 实现关联

- `WikiCatalog`验证公开目录关系与顺序，拒绝重复ID、失效父分类和循环，不补默认分类或虚假文章数。
- `WikiOutline`验证本地渲染返回的标题ID、层级与坐标，提供当前章节判断。
- `WikiReaderNavigation`负责原生目录窗口、章节高亮、外层ScrollView定位及章内偏移恢复；页面代次变化后拒绝旧回调，重复点击保持单窗口。
- `ContentView`与`reader/content.js`保留原Markdown清理、公式和图片阅读边界。仅Wiki启用标题锚点和布局测量；不增加`addJavascriptInterface`，不把登录凭据交给网页。章节位置来自实际渲染布局，动态尺寸变化后重新测量。
- `WebFeaturesActivity`接入分类/路径/标签及页面栈；每个读取区域各自防重，避免新增分类说明请求阻止文章列表请求。站内Wiki路径/章节留在App，外站HTTPS Wiki链接仍交系统浏览器；站内关联练习继续进入原生题面与样例。

普通论坛、评论和题面仍使用原阅读器模式，不能因Wiki目录改动开放原始HTML脚本或通用JS桥。管理员Wiki编辑继续留Web。

## 本地验证

核心逻辑测试为 `WikiNavigationTest`；界面集成为 `WikiNavigationUiSmoke`，由独立测试APK的 `wikinavigation` 模式运行。使用虚构账号、合成HTTPS响应和真实本地WebView，拒绝生产网络，不执行生产写入。

验收覆盖完整目录/文章数/路径/标签、重复标题、代码块排除、脚本清理、目录跳转、上下滚动高亮、章内偏移及转屏/返回、历史版本隔离、动态布局、站内题面、外链、分类失败隔离、空目录与匿名阅读。标题判定允许一个物理像素的取整误差，避免动态排版后刚跳到章节却仍高亮上一章节。

| 检查 | 实测结果 |
| --- | --- |
| JVM单元测试 | 157项全部通过，其中9项为新增Wiki目录/章节契约测试 |
| 本地构建 | `testDebugUnitTest`、`assembleDebug`、`assembleDebugAndroidTest`、`lintDebug`成功 |
| Lint | 0错误、57条原有警告，本轮没有新增警告 |
| API35原生模拟器 | `wikinavigation`、`web`、`problemtags`、`globalsearchadmin`四组全部通过 |
| 界面目检 | 章节栏、目录层级、主题高亮、正文定位与圆角窗口已检查截图 |
| 制品与边界 | 构建副本与最终源码逐文件一致；主APK未混入测试域名/夹具；原比较节点APK哈希未变；`feat/`、`.github/`无变更 |

本地日志为`Android_APP/dist/build-wiki-navigation-final.log`和`Android_APP/dist/ui-wiki-navigation-regression.log`；截图为`Android_APP/dist/ui-account-closure-screens/files/wiki-reader-navigation.png`、`wiki-chapters.png`。这些构建/验证产物不入Git。文档链接与`git diff --check`检查通过。测试使用合成接口，不代表正式服务器或其他Android版本已完成真机验收；未上传PR或发布新安装包。

此前后续本地功能见[原始题目标签](android-problem-tags-local-2026-11-06.md)、[本人OJ绑定](android-oj-bindings-local-2026-11-06.md)和[账户注销](android-account-closure-local-2026-11-06.md)。
