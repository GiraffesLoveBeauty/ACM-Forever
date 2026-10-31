# Wiki 知识手册：实现、运维与验收

实现分支：`feat/codex-wiki-handbook`。本次采用匿名公开阅读、admin/root 在现有后台维护的策略。Wiki 与 OJ 绑定无关；不恢复个人笔记、待复习或提交时间线。文章 Markdown、修订、分类及资源引用保存在后端，页面发布不需要提交 Git。

## 页面与维护流程

- `/wiki.html`：默认大类；左侧只列大类，内容区展示小类卡片及已发布数量。
- `/wiki.html?category=<id>`：大类或小类列表，`page` 保留分页。
- `/wiki.html?slug=<slug>`：当前已发布正文；`#章节` 为可分享目录锚点。
- `/wiki.html?q=<关键词>&page=1`：标题、别名、标签和正文检索。
- `/wiki.html?slug=<slug>&revision=<id>`：允许公开的历史版本。
- `/admin.html?section=wiki&tab=categories`：分类增删改、同级拖动/按钮排序、默认入口、删除影响与恢复。
- `/admin.html?section=wiki&tab=pages&page_id=<id>`：文章列表和编辑。列表支持 `category_id/state/q/page`。

管理员先建大类和小类，再导入或编写文章。图片可选择、拖拽或粘贴，上传前自动建立受保护的文章/论坛草稿身份。正文、标签、别名、练习、来源和许可随修订保存；文章当前分类独立维护。点击“发布文章”才切换公开内容。新增文章可手填 slug 或自动生成，创建后不改；分类改名和迁移保留文章地址。

草稿保存串行执行，保存期间的后续输入继续保存；切换页面时等待保存。关闭或刷新前保留按账号与文章隔离的本地恢复副本，重新进入时可恢复或丢弃。网络或权限失败不能保证服务端保存成功，应保留提示并重试。409 保留编辑内容并展示服务器草稿；管理员比较后显式选择基于最新版本继续编辑。历史回退生成新草稿，需另外发布。历史隐藏不删除内部修订，当前公开版本不能直接隐藏，应先发布替代版本。

读者支持目录、公式、代码复制、相邻多语言示例切换、受控图片键盘/点击放大、关联练习和下载 MD。超宽代码、表格在局部滚动。图片损坏显示占位，未知分类/文章和网络失败提供重试；请求失败保留上次内容。搜索建议防抖 250ms 并取消/忽略旧响应；上下方向键选择、Enter 打开首条建议、Escape 关闭，搜索按钮进入可分享的完整结果页。匿名和成员返回相同公开内容，成员没有维护入口。

## 共享 Markdown 协议

`MarkdownEditor.vue`、`markdown-source.js`、`markdown.js` 与后端 `markdown_content.py/markdown_api.py` 由论坛和 Wiki 共用。保留论坛草稿恢复、串行保存和审核流程；发布话题仍先进入审核。论坛公开话题也提供“下载 MD”。

- 统一 `title/body` 源文本；标题 120、正文 20000 个 Unicode 码点。
- `.md/.markdown` 文件不超过 100KB，严格 UTF-8，去 BOM、换行为 LF。解析首个非代码块 H1 为标题，无 H1 时使用文件名；导入覆盖已有内容前确认。
- 导入不会发布。相对/外站/本机图片显示待关联资源清单，不读取本机路径。
- 图片只允许同源 `/api/markdown/assets/<32位资源ID>`；Markdown 与 HTML 渲染经过 DOMPurify 允许列表，无事件属性或任意嵌入。
- PNG/JPEG/WebP 单张最多 2MB，最长边 4096px，禁止动画；Pillow 实际解码并重新编码去除元数据，随机不可变存储名。上传者、业务类型与真实文档归属由后端核验。
- 公开可读范围来自当前及允许公开的历史修订引用；草稿资源仅授权账号可读，论坛待审核图片不会公开。资源响应使用 `no-store`，避免历史隐藏后公共缓存继续提供图片。
- MD 下载按权限选择源修订，以 `text/markdown; charset=utf-8`、安全 ASCII 文件名、`nosniff` 返回；生成转义后的 H1，保留正文和公式，受控图片转换成配置的本站绝对地址。下载后重新导入可继续编辑。

## 数据与并发

新增结构在 `feat/api/acm_api/wiki.sql`，现有数据库初始化时以 `CREATE ... IF NOT EXISTS` 检查创建，不在普通读取请求中重复升级。重复启动保留原数据；首次创建不会自动生成示例内容。

| 表 | 保存内容 |
| --- | --- |
| `wiki_categories/wiki_settings` | 两级分类、软删除、默认入口、目录/公开版本 |
| `wiki_pages` | 稳定 slug、当前分类、草稿/公开指针、文章版本 |
| `wiki_revisions` | 不可变正文、版本元数据、作者、发布与隐藏标记 |
| `wiki_search` | 当前公开修订的标题、别名、标签和正文检索副本 |
| `wiki_category_operations/wiki_delete_previews` | 操作前后快照、恢复审计、短期删除凭据 |
| `wiki_requests` | 发布/删除的操作者、操作、幂等键及原响应 |
| `markdown_assets/markdown_asset_references` | 不可变资源元数据及 Wiki/论坛引用 |

数据库约束阻止超过两级的分类、同级规范化重名、文章挂大类、跨文章修订指针及改写历史正文。目录写入核对 `navigation_version`；文章保存同时核对 `version/base_revision_id`。写操作用 SQLite `BEGIN IMMEDIATE` 事务，发布时切换公开指针和检索副本。

删除凭据有效 5 分钟，绑定操作者、目标和全目录/文章版本指纹。新增文章、保存草稿或调整目录都会使旧预览失效。非空大类把整个小类迁入另一大类，保留小类 ID；非空小类把文章迁到另一小类。重名或目标失效时全事务回滚；默认入口替换和软删除在同一事务。恢复检查删除后的快照，后续编辑、迁移、重名等冲突不会被覆盖；当前实现保守地在目录/公开状态变化后拒绝自动恢复，需要管理员人工核对。

中文检索使用参数化 LIKE 兜底，不依赖英文分词；匹配优先标题、别名、标签，再正文。每页默认 20、上限 50，关键词上限 100。规模较大时需要再评估 FTS/中文分词。公开 JSON 使用基于响应内容的 ETag 和 `max-age=0, must-revalidate`；草稿保存不改变公开列表时间、正文或 ETag。私有维护接口和下载不进入公共缓存。

## API 合约

所有维护写请求使用现有 Cookie 与 `X-CSRF-Token`，仅 admin/root；图片上传为成员接口，Wiki 类型另查管理权限，论坛类型另查草稿归属。公开接口不返回草稿标题/数量和管理员内部备注。统一错误为 `{message, code}`，400 参数错误、401 未登录、403 权限/CSRF、404 不可访问、409 并发/约束冲突、413 超限。

公开读取：

| 方法 | 路径 | 参数/结果 |
| --- | --- | --- |
| GET | `/api/wiki/navigation` | 大类/小类与已发布数量、默认入口 |
| GET | `/api/wiki/categories/<id>` | 分类、真实路径、小类 |
| GET | `/api/wiki/pages` | `category_id/page/page_size` |
| GET | `/api/wiki/search` | `q/page/page_size` |
| GET | `/api/wiki/pages/<slug>` | 当前公开修订、真实分类路径及元数据 |
| GET | `/api/wiki/pages/<slug>/revisions` | 最多 100 条允许公开的发布历史 |
| GET | `/api/wiki/pages/<slug>/revisions/<id>` | 指定公开历史正文 |
| GET | `/api/wiki/pages/<slug>/markdown` | 当前源文本；可用 `revision_id` 选公开历史 |

管理员：

| 方法 | `/api/admin/wiki` 后的路径 | 请求要点 |
| --- | --- | --- |
| GET/POST | `/categories` | POST：`name/description/parent_id/version` |
| PATCH | `/categories/<id>` | 修改/迁移，`version` 为目录版本 |
| PUT | `/categories/order` | `parent_id/ids/version`，必须完整同级集合 |
| PUT | `/settings` | `default_category_id/version`，允许无默认入口 |
| POST | `/categories/<id>/delete-preview` | `{}`，返回影响、目标、token |
| POST | `/categories/<id>/delete` | `token/target_id/default_category_id/idempotency_key` |
| POST | `/category-operations/<id>/restore` | `{}`，冲突拒绝覆盖 |
| GET/POST | `/pages` | GET：`category_id/state/q/page/page_size`；POST：小类、slug 和内容 |
| GET/PATCH | `/pages/<id>` | PATCH 只改 `category_id`，带文章 `version` |
| GET/POST | `/pages/<id>/revisions` | POST：源字段、版本元数据、`version/base_revision_id` |
| GET | `/revisions/<id>` | 内部修订及元数据 |
| POST | `/revisions/<id>/publish` | `version/idempotency_key`，只能发布当前草稿 |
| PATCH | `/revisions/<id>` | `version/hidden`，显式控制历史公开 |
| POST | `/pages/<id>/restore` | `revision_id/version/base_revision_id` |
| GET | `/revisions/<id>/markdown` | 授权源修订下载 |

共享资源：`POST /api/markdown/assets` 使用 multipart `file/document_type/document_id`；业务类型为 `wiki` 或 `forum_draft`。成功 201 返回 `id/url/size/width/height`。`GET /api/markdown/assets/<id>` 按引用权限返回图片或 404。论坛下载为 `GET /api/forum/posts/<id>/markdown`（仅公开帖子）及 `GET /api/forum/drafts/<id>/markdown`（仅本人）。

发布和删除的 `idempotency_key` 长度 8–100，相同操作者/操作/键和请求体重试返回原结果，不重复执行；同键不同请求返回 409。创建文章返回编辑状态，新增修订返回新的文章版本与草稿指针。客户端需使用响应值发起下一次写入。

## 合并前准备与持久化

`main` 中的 `feat/**` 改动会触发部署。以下是待运维执行的发布准备，开发验证不表示已部署。

1. 在隔离环境使用实际备份副本演练升级与恢复；由另一位成员评审 PR。
2. 设置 `ACM_DATABASE_PATH` 到代码同步目录之外，例如 `/home/WYJ/acm-forever-data/acm_forever.db`。
3. 配置 `ACM_MARKDOWN_UPLOAD_DIR=/home/WYJ/acm-forever-data/uploads/markdown`；省略时默认数据库同级 `uploads/markdown`。不要放进 `web/dist` 或镜像同步目录。
4. 配置 `ACM_PUBLIC_BASE_URL=https://实际站点域名`，只接受协议和主机（可带端口），不带路径、用户名、查询。外部站点未配置时 MD 下载返回 503；仅 loopback 开发环境可回退本机地址。
5. 安装更新后的 `feat/api/requirements.txt`（含 Pillow），前端执行 `pnpm install --frozen-lockfile`、`pnpm build`。
6. 核对反向代理允许至少 3MB 请求；服务总请求上限仍为 3MB、单图 2MB。仅代理 API 图片路径，不把图片目录作为静态目录匿名公开。
7. 服务账号对数据库和上传目录拥有写权限；启动后检查健康、Wiki 空状态/既有内容、草稿保存、图片读取、发布、检索及下载。

备份必须同时包含 SQLite 与资源目录。推荐暂停写入/停服后完成一致备份：记录代码提交、环境配置键、数据库文件与完整 `ACM_MARKDOWN_UPLOAD_DIR`，再复制到受控备份位置。运行中单独复制 `.db` 可能遗漏 WAL；若使用 SQLite 在线 backup，也要固定同一时间点的资源清单，避免清理与备份并行。

回退时先停服和保存故障现场，按记录恢复代码与匹配的数据库、完整资源及环境配置，再启动检查。新表为增量创建，普通代码回退不会自动删除新数据；不得通过删表当作自动降级。恢复后的权限、公开版本、历史图和新增上传需再次验证。

## 临时图片的人工清理

默认没有定时删除资源。维护工具先列清单，宽限期最少 7 天；所有存在的 Wiki 修订（包括隐藏历史、内部草稿）和现有论坛话题/草稿引用都保留。不会扫描删除未知文件。

在仓库根目录、停服并备份后执行：

```powershell
python -m feat.api.acm_api.markdown_cleanup --database "D:/持久化/acm_forever.db" --uploads "D:/持久化/uploads/markdown"
# 核对清单后才加 --apply 执行
python -m feat.api.acm_api.markdown_cleanup --database "D:/持久化/acm_forever.db" --uploads "D:/持久化/uploads/markdown" --apply
```

生产部署目录本身为 `feat/` 时，模块名相应为 `api.acm_api.markdown_cleanup`。清理前再次用写事务核验引用，路径必须位于指定资源目录。清理属于人工运维步骤，本次未对生产或个人资源执行。

## 验证方式

```powershell
python -m unittest discover -s feat/api/tests -p "test_*.py"
cd feat/web
pnpm test
pnpm build
```

`test_wiki.py` 使用临时数据库和真实 Cookie，验证权限/CSRF、公开草稿隔离、中文与别名检索、并发与幂等、类别迁移/恢复冲突、真实图片解码及历史引用、MD 源文下载、ETag 和重复初始化。`wiki.test.mjs` 挂载真实组件与路由，验证共享导入/渲染、失败保留、图片重试/取消、阅读路由/迟到响应、草稿串行保存、409 处理、离开目标保留及论坛草稿兼容。

本次独立合成数据环境的运行记录、截图、预览程序与数据库均保存在仓库外。真实浏览器验收覆盖导入→图片→保存→发布→匿名/成员阅读→下载→重新导入、删除迁移恢复、双标签冲突、登录/改密返回、320/736/1024/1440px 与原有设计、相变信号、天使之城三套主题的深浅色。重启检查使用同一外部数据库和图片目录。具体运行结果由本次 PR 的验证记录列明；上线仍需团队评审和运维确认。

### 基础版本验收记录（2026-10-31）

任务从本地 main `bcd15eb` 开始；开发期间 main 合入“天使之城”，已将 `origin/main` 的 `e575db2` 同步进任务分支，保留全部主题导入，并增加新主题兼容验收。

- API 回归 84 项，其中 Wiki/共享资源专项 14 项；Vue 回归 79 项，其中 Wiki 与共享编辑器 12 项；原有脚本 31 项；生产构建通过。
- 浏览器先完成分类、MD 导入、三种图片上传、发布、阅读、源码下载/重新导入、草稿隔离、回退、删除迁移恢复及双标签冲突，再补充真实登录/首次改密返回、论坛审核/下载及三套主题矩阵。阅读宽度为 320/736/1024/1440px；后台另检查 320/1024px 深浅色。
- 独立新进程加载同一外部数据库和图片目录，公开正文、分类路径、修订/资源计数、图片 SHA-256 均一致；交付预览进程另经停止、重启后复查。
- 所有运行材料和合成示例库均在项目外，未访问真实 OJ、真实成员数据或生产服务。发布仍按工程规范由其他成员评审及运维确认后进行。


### 体验包界面迁移（2026-10-31）

依据用户提供的 `Wiki预览体验包-20261031.zip` 调整正式 Vue 界面，复用真实 API、鉴权与已有 Markdown 能力。离线原型的角色切换、预览宽度和恢复演示数据等工具仅用于参考，不进入正式产品；没有增加离线原型中的内嵌运行库或新的前端依赖。

- 阅读端：搜索工具栏、大类导航及公开数量、深色介绍卡片、编号小类卡片、近期公开文章；没有摘要的条目从 Markdown 摘取纯文本。
- 搜索：建议浮层保留当前阅读位置，方向键/Enter/Escape 可操作；完整搜索结果保留 `q/page` 参数。旧响应不会重新打开已关闭的建议浮层。
- 文章：`tab=practice` 切换关联练习，默认阅读讲解；切换标签或章节不重新加载文章，前进、后退和刷新保留对应状态。右侧展示本篇目录、当前分类与真实标签，不编造未配置的先修知识。
- 手机：大类使用原生模态抽屉，支持触摸、焦点约束、Escape、关闭按钮及选中后关闭；文章目录可展开。代码和表格保持局部滚动。
- 分类管理：仍在统一管理中心内部运行；大类导航驱动当前大类及小类列表，`/admin.html?section=wiki&tab=categories&category=<id>` 保留选择；新建/迁移后选中对应大类，失效选择回到有效默认入口。
- 分类编辑和删除面板显示在内容上方。未保存分类输入有离开保护；同级拖动和上下移按钮均可排序，首尾按钮禁用。删除前展示真实影响、接收目标及默认入口，成功后可撤销并核对恢复记录。
- 补齐空白 Wiki 首次图片上传的串行保存：更新新草稿 URL 时不再触发竞争刷新，避免上传前的保存被取消。Wiki 上传者失去管理角色后不保留私有 Wiki 图片访问或转用权限；本人论坛草稿图片继续沿原权限访问。

体验包首轮测试结果保存在项目外；该阶段源码仅保留于 `feat/codex-wiki-handbook` 本地工作区，尚未提交、推送或更新 PR。后续集成状态见下文。

本轮验证：API 85 项、Vue 88 项（Wiki/共享编辑器 21 项）、真实浏览器 93 项全部通过，生产构建与格式检查通过。三套主题均检查深浅色；阅读宽度 320/390/736/1024/1440px，管理宽度 320/736/1024/1440px，无页面横向溢出。体验服务使用独立合成数据，未访问生产或真实 OJ。


### 体验包审核修复（2026-10-31）

- 搜索快捷键在 `isComposing` 为真或兼容键码为 `229` 时直接返回，组词期间的 Enter、方向键和 Escape 留给输入法处理；确认候选词后恢复正常搜索及快捷键。
- 分类未保存保护按导航范围分工：管理后台外壳负责离开后台及切换管理模块，分类组件负责同一 Wiki 模块内的标签和大类切换。一次导航只询问一次；拒绝后保留原地址与表单，接受后清理已放弃状态。
- 增加 6 项回归：两种输入法事件路径，以及真实 Admin → 异步 Wiki → 分类组件组合中的四种导航方向。组合测试同时验证拒绝和接受，不再仅独立挂载分类组件验证离开后台。

修复后重新运行：Vue 全量 94/94，其中 Wiki/共享编辑器 27/27；本地 Edge 边界检查 32/32，脚本错误 0；生产构建、前端格式和差异空白检查通过。浏览器输入法验证使用合成 composition/keyboard 事件，没有执行系统输入法人工操作。本次边界检查未改动合成分类数据。

此前 API、完整视觉矩阵及 93 项浏览器记录保留为上一轮验证结果，本次未重复执行。新增脚本、日志与修复记录继续放在项目外的 `wiki-design-20261031` 目录；当轮修复仍保留在本地，后续集成状态见下文。


### PR 集成验收（2026-11-01）

上述体验包界面与审核修复通过现有 PR #63 交付，源码、测试和文档分开提交。任务分支通过普通合并包含 Minecraft 主题及 AtCoder 旧题面样例修正，集成基线为 `origin/main` 的 `3aa61cb`。入口文件同时保留 `minecraft-theme.css` 与 `wiki.css`；未改写已有分支历史。

本次集成重新执行 API 全量 89/89（Wiki/共享资源 15 项）、Vue 全量 97/97（Wiki/共享编辑器 27 项）、原有脚本 31/31，以及生产构建、前端格式和差异空白检查。浏览器边界复查继续覆盖组词按键、正常快捷键、四种分类离开方向及前进后退，共 32 项通过，脚本错误 0。输入法仍以合成事件验证。

Minecraft 兼容检查在前一轮主题同步后完成：总览、文章、后台分类管理覆盖 320/390/736/1440px 的深浅色，共 24 个布局组合及 8 项补查通过，像素字体、材质和移动抽屉正常。本次新增 AtCoder 同步没有调整 Wiki 或主题样式；此前的完整视觉与图文持久化验收记录保留为对应阶段结果。

验收脚本、日志、截图与数据库继续保存在项目外。PR 保持草稿；合并前仍需其他成员评审及运维确认发布条件。
