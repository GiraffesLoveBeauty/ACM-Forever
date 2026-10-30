# 个人主题开发与投稿规范

状态：本次主题库功能的实现说明与投稿约定；随代码评审，不替代小组工程规范。适用范围为 `feat/web`，工程流程以 [TCrB-AI项目工程规范.md（工程协作规范 · 讨论稿）](TCrB-AI项目工程规范.md) 为准。

## 1. 主题、配色与分类

- **设计模板**控制视觉结构、装饰、边框与布局风格。已有 `original`（原有设计模板）和 `phase`（相变信号）。默认仍为原模板。
- **配色方案**控制模板内的浅色、深色与自定义颜色，可在“自助调色”编辑、导入、导出和收藏。
- **分类**只组织主题库展示。已有默认、明日方舟、原神、绝区零；没有模板的分类显示空状态，不创建虚假的可用主题。
- 浏览分类不会改变当前模板。点击模板才应用，并恢复该模板独立保存的配色和收藏。

“相变信号”参考明日方舟视觉语言，归入明日方舟分类。它不替换其他分类或原有模板，也不表示官方授权或联名。

## 2. 个人编辑与 JSON 分享

1. 打开页头“主题库”，选择准备编辑的模板。
2. 打开“自助调色”，分别编辑浅色与深色，选择保存模式或跟随系统。
3. 颜色输入和预设选择先进入草稿；保存主题才持久化。“仅本页应用”不写入当前配色存储；在本页来回切换模板仍保留，刷新后恢复已保存方案。
4. “恢复此模板原配色”恢复当前模板的默认草稿，点击保存确认；取消、关闭或 Esc 撤销未保存预览。
5. 使用“导出 JSON”分享配色。接收者先选择对应模板，再导入、预览和保存。当前导出文件不包含模板 ID、样式源码或收藏库，分享时须另行注明适用模板。

配色 JSON 使用现有 `version: 1` 结构，最多 32768 字节。仅接受 `version/mode/light/dark` 与允许的颜色字段，颜色为 RGB 十六进制。示例：

```json
{
  "version": 1,
  "mode": "system",
  "light": {
    "colors": {
      "primary": "#202629",
      "background": "#e7e8e5",
      "surface": "#f8f9f6",
      "accent": "#d5f500"
    },
    "overrides": { "hero": "#151a1d" }
  },
  "dark": {
    "colors": {
      "primary": "#e4ece9",
      "background": "#101619",
      "surface": "#1d2529",
      "accent": "#d5f500"
    },
    "overrides": { "hero": "#11171a" }
  }
}
```

高级覆盖字段为 `text/muted/border/link/selected/hero`。不在 JSON 中加入 HTML、CSS、脚本、远程地址或个人信息。浏览器导入只保存本机偏好，不会将模板上传到服务器或发布到公共主题库。

## 3. 完整模板的文件和登记

相关入口：

| 文件 | 职责 |
| --- | --- |
| `feat/web/src/lib/design-template.js` | 分类、模板元数据、默认配色、独立存储键 |
| `feat/web/src/components/TemplateLibrary.vue` | 分类、缩略示意、选用状态与投稿说明 |
| `feat/web/src/components/ThemeEditor.vue` | 模板内配色编辑、保存与收藏隔离 |
| `feat/web/src/components/Header.vue` | 主题库入口与模板选择 |
| `feat/web/src/phase-theme.css` | 相变信号样式示例 |
| `feat/web/src/components/GraphArt.vue` | 已有十二节点图谱与非交互装饰 |
| `feat/web/src/main.js` | 新模板样式导入入口 |

新作者的操作顺序：

1. 检查工作区，从共同主分支建立短期任务分支。命名参考仓库建议 `<类型>/<负责人ID>-<任务简述>`；本次开发分支为 `codex/phase-community-theme`。
2. 在 `TEMPLATE_CATEGORIES` 复用合适分类；确需新分类再添加唯一分类 ID 和中文名称。
3. 在 `DESIGN_TEMPLATES` 添加模板记录。ID 使用稳定、唯一的小写英文与连字符，例如 `genshin-dawn`；不要改用显示名称作为 ID，也不要复用其他模板 ID。
4. 在 `templateTheme` 为该 ID 返回完整浅深默认配色，原模板分支保持原值。默认值必须通过 `validateTheme`。
5. 新建独立样式文件，从 `main.js` 导入；补充缩略示意样式。当前 `preview` 是 `TemplateLibrary.vue` 内的 CSS 类型，不是任意图片 URL；新增类型须同时实现对应样式。
6. 若确需共享组件提供装饰挂点，默认隐藏，只在目标模板范围显示；不将新主题结构硬编码到业务逻辑。

登记示例（仅供新模板开发参考，不代表原神模板已经实现）：

```js
// TEMPLATE_CATEGORIES 中已预留 genshin，无需重复添加。
{
  id: 'genshin-dawn',
  category: 'genshin',
  name: '晨光',
  description: '说明本模板的视觉特点。',
  preview: 'genshin-dawn',
}
```

CSS 示例：

```css
html[data-design-template='genshin-dawn'] body.endfield-design .forum-welcome {
  border-radius: 12px;
  background: var(--hero-bg);
  color: var(--hero-text);
}
```

需要覆盖共享自助调色适配规则时，可增加 `html[data-custom-theme][data-design-template='genshin-dawn']` 的限定。避免通过无范围的 `body`、`button`、`a` 或通用组件选择器改变其他模板。主题库面板属于共享选择界面，新增主题不应让它失去可用性。

## 4. 独立存储与兼容

| 内容 | 原模板 | 其他模板（例如 phase） |
| --- | --- | --- |
| 模板选择 | `acm.design-template.v1` | 同一选择键，只存当前模板 ID |
| 当前配色 | `acm.theme.v1` | `acm.theme.<id>.v1` |
| 收藏方案 | `acm.theme.library.v1` | `acm.theme.<id>.library.v1` |

必须使用 `themeStorageKey` 和 `libraryStorageKey`，不要在组件中为新模板复制硬编码的配色键。原有存储格式、工业黄/清绿等预设与 legacy 明暗兼容保留。未知或已下线的模板 ID 回退原模板；不能因此清空用户偏好。

运行时模板状态由 `ThemeEditor` 统一持有，模板选择也由其 `setTemplate` 持久化。其他组件通过 App 提供的 `getDesignTemplate` 在 `computed` 中读取，通过 `setDesignTemplate` 切换；不要再建一份本地模板状态或自行写入选择键。切换前保留已应用方案，装载新模板后再关闭编辑草稿，避免重新应用旧模板。

仅属于某个模板的装饰按响应式模板状态条件挂载，切换时不重建图谱等业务组件。模板标识和样式门控属性的设置不依赖配色计算成功；非法草稿保留最近一次有效配色并显示错误，不能静默改变所选模板。

存储受限时允许仅本页使用。切换模板前撤销未保存的编辑草稿，当前已应用方案在本页会话保留。不要把模板默认色写回另一个模板的存储空间。

## 5. 功能、资源和可用性要求

- 保留现有角色权限、路由、数据接口、搜索、分类筛选、排序、分页与帖子操作，不为展示效果伪造业务功能或线上统计。
- 核对登录/未登录、浅深模式、加载/失败/空状态；正文、次要文字与按钮均需可读。颜色不能是选中状态的唯一标志。
- 图谱继续支持十二节点点选、Enter/空格、Esc 复位、可见键盘焦点。装饰元素设为非交互，不遮挡链接和命中区。
- 检查 390px、768px、1280px 以及桌面布局，不产生页面横向溢出；弹窗可滚动、有关闭入口，Esc 后焦点返回打开按钮。
- 尊重 `prefers-reduced-motion`，避免持续大幅动画或用斜排小字承载必要信息。
- 素材须有可说明的来源与使用权限。提交自绘、本地或已授权资源；不得把游戏截图、人物立绘、字体或音乐在未确认权限时直接打包。记录来源、用途和修改，保留所需许可声明。
- 不提交密码、真实账号、个人信息、数据库、预览脚本、运行日志、效果图或开发环境。生成设计稿只是参考；本次上线界面使用源码绘制。

## 6. 投稿、验证与发布

公共模板采用 **源码分支 → PR → 跨人评审 → 非提交者合并** 的流程。当前没有公共模板文件上传 API、自动安装任意 CSS/JS 或个人作品审核后台；不要将本地 JSON 导入称为公共发布。

PR 应包含：模板及分类、作者标识、改动范围、默认配色、素材说明、操作方式、真实测试结果、已知限制。建议标题 `feat(web): add <name> theme template`。源码、必要资源、测试与文档进入同一 PR，文档可独立提交。

在仓库根目录执行与本次改动相关的检查：

```powershell
pnpm --dir feat/web build
pnpm --dir feat/web test
node --test feat/api/tests/theme-colors.test.cjs feat/api/tests/theme-performance.test.cjs
git diff --check
git diff --cached --check
```

按 [api-tests.yml（自动检查）](../.github/workflows/api-tests.yml) 的实际路径触发 CI；本地通过不能写成远端 CI 已通过。`pnpm test` 自动发现 `tests/*.test.mjs`，其中 `theme-templates.test.mjs` 验证真实编辑器和分类组件的行为。

浏览器验收至少覆盖：首次默认、按分类浏览、空分类、应用模板、原模板恢复、刷新持久化、独立配色/收藏、取消/恢复默认、存储受限、手机布局和键盘操作。使用独立合成数据库；演示文件放在根目录忽略的 `data/`。

`feat/**` 合入 `main` 会触发现有自动部署。合并前完成成员评审、CI、相关联调及运维发布确认；提交者不自行合并，不直接推送或强推 `main`。有新提交时检查对应新版本。若需要撤回发布，通过新的修复/撤销 PR 执行，并由运维验证；本功能无数据库迁移，浏览器旧存储键应保留。

## 7. 相变信号本次交付范围

包含分类主题库、制作投稿说明、原模板与相变信号的独立配色/收藏、CSS/SVG 装饰与响应式布局。原神和绝区零仅预留分类。无新增后端 API、账号同步、公共上传服务、数据库结构或第三方素材依赖。

设计研究来源为用户提供的三张界面截图和 [ignoredone 明日方舟美术资源系统](https://www.ignoredone.space/index.php/arknights_design/)。网页动态资源未完整提取，设计观察以用户截图为主；发布源码不附带参考截图或 AI 生成效果图。
