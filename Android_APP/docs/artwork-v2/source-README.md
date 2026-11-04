# ACMforever 猫娘素材包 v2

面向 Android 应用「打一辈子爱臭美 / ACMforever」的可换色猫娘素材包：头像、敲代码加载插画、剪影，含真实分层、中性灰换色图层、遮罩、主题预览与文件清单。

## 一、素材来源与生成方式

- 原图来源：用户提供的 `原图/1.png`（头像）、`原图/2.png`（加载插画）、`原图/3.png`（剪影），随 `ACMforever_美术修改交接_v1.zip` 提供。
- 实际使用的平台与模型：本机 Codex / DeepSeek Harness 环境，通过 MCP `imagegen` 中转调用 **gpt-image-2** 的图像编辑接口（`edit_image`），把原图作为图像输入逐张重绘。本次交付的 v3 批次实际调用 3 次（avatar / loading / silhouette），**不是**只写提示词或程序描摹。
- 模型原始输出保存在 `sources/model-raw/`，可直接对比。

| 文件 | 来源 |
| --- | --- |
| `sources/model-raw/*-v3.png` | gpt-image-2 直接输出（未改动） |
| `avatar/reference.png`、`loading/reference.png`、`silhouette/silhouette.png` | 模型输出 + 后处理：alpha 归一化（内部补满 255、背景归 0）、边缘去白/去黑残色、剪影合并碎镂空并简化轮廓 |
| `*/layers/original/*.png` | 后处理：由 reference 做部件分割后逐层导出（同画布、同原点、透明 RGBA） |
| `*/layers/neutral/*.png` | 后处理：对应图层求灰阶，alpha 完全一致 |
| `*/masks/*.png` | 后处理：由同组真实图层的 alpha 合成，非按像素猜色 |
| `*/previews/*.png` | 后处理：中性灰图层按主题色重新着色后合成 |
| `contact-sheet.png` | 后处理：原配色与四套主题的对照表 |

## 二、图层与换色分组

颜色组：`hair_eyes`（头发与眼睛）、`clothes`（衣服主体）、`decor`（蝴蝶结与装饰）可独立换色；`fixed` 保留肤色、脸颊、猫耳、领子、袖口花纹、电脑原色。眼睛在预览里只带很轻的同色倾向，保持接近黑色。

图层按 **从后到前** 叠放，`manifest.json` 中 `layers` 数组顺序即绘制顺序。

### avatar（1024×1024）

| # | 图层文件 | 部件 | 颜色组 | 中性灰 |
| - | --- | --- | --- | --- |
| 1 | `01-hair-back.png` | hair-back | hair_eyes | 有 |
| 2 | `02-clothes.png` | clothes | clothes | 有 |
| 3 | `03-collar.png` | collar | fixed | — |
| 4 | `04-face.png` | face | fixed | — |
| 5 | `05-hair-front.png` | hair-front | hair_eyes | 有 |
| 6 | `06-headband-ears.png` | headband-ears | fixed | — |
| 7 | `07-eyes.png` | eyes | hair_eyes | 有 |
| 8 | `08-decor-bow.png` | decor-bow | decor | 有 |

### loading（1536×1536）

| # | 图层文件 | 部件 | 颜色组 | 中性灰 |
| - | --- | --- | --- | --- |
| 1 | `01-hair-back.png` | hair-back | hair_eyes | 有 |
| 2 | `02-clothes.png` | clothes | clothes | 有 |
| 3 | `03-collar-cuffs.png` | collar-cuffs | fixed | — |
| 4 | `04-laptop.png` | laptop | fixed | — |
| 5 | `05-face.png` | face | fixed | — |
| 6 | `06-hands.png` | hands | fixed | — |
| 7 | `07-hair-front.png` | hair-front | hair_eyes | 有 |
| 8 | `08-headband-ears.png` | headband-ears | fixed | — |
| 9 | `09-eyes.png` | eyes | hair_eyes | 有 |
| 10 | `10-decor-bow-chest.png` | decor-bow-chest | decor | 有 |
| 11 | `11-decor-bow-hair.png` | decor-bow-hair | decor | 有 |

> `hair-front` 是覆在额头前的刘海，`hair-back` 是两侧与后方的长发，两者同属 `hair_eyes`，拆分只用于表达遮挡顺序。`fixed` 各组之间的边界是几何近似的（它们不参与换色，逐层叠加仍与 reference 完全一致）。

## 三、推荐配色与预览

| 主题 | 主色 |
| --- | --- |
| 薄荷 | `#82C7AA` |
| 天蓝 | `#83B8E5` |
| 樱粉 | `#EBAFC5` |
| 黄绿 | `#C8EB21` |

每套主题里头发取主色加深、衣服主体取主色提亮、装饰取偏移色作点缀，三组之间保留层次；肤色、猫耳、领子、袖口花纹、电脑在所有预览中保持原色。预览仅为展示，最终素材本身是透明背景，没有把预览底色合进图层。

## 四、已完成的检查

- 所有图层与 reference 同尺寸、同原点，全部为带 alpha 的 sRGB PNG，透明处无黑/白底残边。
- 按 `manifest.json` 顺序用正常 alpha 叠加 original 图层，可 **逐像素完全重建** reference（RGB 与 alpha 差值均为 0，已实际合成验证）。
- 每个换色组遮罩与该组图层 alpha 完全一致，遮罩边缘来自真实图层，而非重新按颜色猜范围。
- 剪影为单色 `#0A0A0A` 形状配透明背景，已合并内部碎镂空并简化轮廓，附 24px / 48px 预览；24px 下仍能看出猫耳轮廓。
- 头像按圆形安全区重新排版：头部（含两只猫耳）完整落在内切圆 94% 半径以内，圆形裁切不会切到耳朵。

## 五、动画

**仅静态素材**：未交付逐帧敲键盘动画。原图与模型输出都是单帧，凭空生成 8～12 帧无法保证手部结构正确、逐帧一致、首尾循环，因此按要求不把未完成的动画当成品。加载插画可直接静态使用；后续如需要动画，建议在同一套图层上做骨骼/部件位移，而不是重新生成整帧。

## 六、已知限制

1. `sources/` 里提供的是 Inkscape 可编辑的图层文档（`avatar.svg`、`loading.svg`、`silhouette.svg`），图层内容引用 PNG 图层；**没有** PSD/KRA 像素图层，因为本环境无法写出这两种带真实图层信息的格式。
2. 分层由「颜色族判定 + 区域生长 + 几何规则」半自动完成，再逐张目视校对；不是手工逐笔重新描线，因此个别极细发丝或 1px 抗锯齿像素仍可能被归到相邻部件。
3. 剪影由模型输出简化而来，属于同角色的识别性剪影，不是原图的精确描摹。

## 七、接入建议

1. 按 `manifest.json` 的 `layers` 顺序、以正常 alpha 合成即可得到原配色画面。
2. 换色：取该组 `layers/neutral` 的明度，乘以目标色（或用 `masks` 做整组着色），可保留全部高光与阴影；眼睛建议保持深色。
3. 桌面图标用白色底 + 黑色剪影，剪影文件本身透明，可在应用内再染主题色。
