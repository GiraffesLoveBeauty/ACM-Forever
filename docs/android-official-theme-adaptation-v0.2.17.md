# 官方主题文件解析与 Android 采用范围（v0.2.17）

状态：源码实现及本地验证，待跨人review。网页源文件只读，没有改网页、后端或自站发布配置。

## 主题不是只有四个颜色

网页官方库入口是 `feat/web/src/lib/design-template.js`，有四套实际模板，其他分类可以为空。`templateTheme(id)` 提供完整浅/深模式的配色；`theme-colors.js` 的 `deriveTokens(profile,dark)` 派生文字、线条、链接、横幅、图谱节点/路径、代码框和状态色等完整 CSS tokens。单独导出的配色 JSON 不携带模板源码，不能仅靠它复现模板。

v0.2.16 已同步配色和覆盖字段，但背景、横幅部分仍由 Android Canvas近似表现，没有直接执行完整模板 CSS/Vue/SVG。v0.2.17 增加本地官方主题层，直接编译和读取源资源，不描摹 SVG、不截图贴图、不重新设计源图案。

| 源文件 | 内容与本轮采用方式 |
| --- | --- |
| `design-template.js` | 官方分类、ID、名称、说明、浅深配色；目录同步至 `web-designs.json` |
| `theme-colors.js` | 原 `deriveTokens` 直接打包执行，主题层使用全部派生变量 |
| `endfield-theme.css`、`style.css` | 原模板样式、背景与共享装饰；直接编译进入本地 CSS |
| `phase-theme.css` | 黑白信号、青/蓝/洋红轨道与三角图案；原CSS在目标模板生效 |
| `angel-city-theme.css` | 网格、钴蓝坐标、浅光背景和建筑样式；原CSS直接执行 |
| `minecraft-theme.css` | 原泥土背景、物品槽及像素风规则，原字体路径由构建器解析 |
| `GraphArt.vue` | 原十二节点、边权、最短路径交互与模板装饰，直接编译进横幅 |
| `AngelCityArt.vue` | 原建筑、网格、镜像等高线SVG，作为官方组件依赖保留 |
| `MinecraftArt.vue` | 原方块地形、树与工作台SVG，作为官方组件依赖保留 |
| `CommunityArt.vue`、`MinecraftPodium.vue`、`MinecraftJourney.vue` | 原排行榜/个人展示装饰组件；对应场景由同一渲染器承载 |
| `forum-graph.css`、`community-art.css` | 图谱、阶梯/轨迹的原始显示规则 |
| `assets/minecraft/dirt.svg`、`hero-halftone.svg` | 原SVG资源，构建解析为本地资源，不用近似平铺重画 |
| `assets/fonts/fusion-pixel/` | 原像素字体供网页主题层使用，随包附OFL许可 |

原神、绝区零目前是空分类，不显示虚构模板；用户导入颜色方案也不获得任意脚本执行能力。

## 应用范围与边界

- 官方背景：背景模式为纯色、跟随主题、主题来源为web时，在页面内容区域加载原CSS背景。状态栏仍有独立表面；自定义纯色/渐变/图片优先，官方背景不遮盖用户图片。
- 官方横幅：通过 `HomeBanner` 加载原GraphArt或展示组件，保留原节点点击与键盘规则。官方场景不再叠加近似的 `HeroBackdrop`；ACMForever原生主题保留原生图谱。
- 实时应用：切色后给已存在的主题层传入新的profile，Vue更新颜色，保留当前页面；不依靠跳转刷新套色。
- 我的主题缩略图：使用保存主题自己的作用域读取配色与背景；点击缩略图与名称执行同一应用流程。
- 原生Android文字、按钮、列表、搜索、底部目录继续由现有 `ThemePalette/MobileStyle` 适配主辅色、覆盖和透明度。Android View **不能直接执行网页DOM选择器**，网页三栏布局、CSS悬停、物品槽按钮内阴影和像素字体不会因此自动覆盖所有原生控件。本轮没有把整套业务页面替换成Web页面，也不把这一边界写成完整CSS原样移植。

官方主题层只渲染打包的仓库资源，不装载远程站点、不持有原生JS桥、Cookie登录桥或管理Token。CSP限制连接为none；WebView禁止文件/内容访问和混合内容；仅允许拦截的固定appassets路径，其他请求拒绝。输入只来自已验证的配色JSON和模板ID。

## 构建和维护

```powershell
pnpm --dir feat/web install --frozen-lockfile
python Android_APP/tools/sync_web_theme_catalog.py --ref origin/main
python Android_APP/tools/build_theme_renderer.py
python -m unittest discover -s Android_APP/tests -p 'test_theme_renderer*.py' -v
```

构建源入口是 `Android_APP/theme-renderer/`，直接import仓库的原组件和CSS；压缩运行资源位于 `Android_APP/app/app/src/main/assets/themes/renderer/`，供离线APK使用。`sources.json`逐项记录源文件SHA256（文本统一LF换行，二进制保持原字节）；Android CI在源码资源变化但未重建时失败。Vue使用MIT，像素字体使用OFL，许可随资源一起打包。生成包不包含截图或研究素材。

目录同步固定到 `origin/main 1c89408122e99986b22efe9fd14e07e49f1c1757`。页面样式与组件使用当前受审分支的只读Web源码，source fingerprints是准确依据；后续Web改主题，需要重新编译并重新review Android资源，不能把离线副本描述为自动追踪远端。

本次运行资源约1.05MB未压缩，其中像素字体约702KB；主题导出包不重复携带这些内置资源。用户自己的原图决定私人主题包的主体体积。验证与已知限制见 [v0.2.17](android-v0.2.17.md)。
