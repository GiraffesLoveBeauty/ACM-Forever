# 缝合像素字体 / Fusion Pixel Font

方块工坊使用支持简体中文的 12px 比例字体，文件未经修改或子集化。本地提供 WOFF2，浏览器无需向字体 CDN 发起请求；常用正文与控件使用 14px，图谱小字保持 12px，主要标题使用 24px / 36px / 48px。

- 来源：[TakWolf/fusion-pixel-font](https://github.com/TakWolf/fusion-pixel-font)
- 版本：[2026.10.25](https://github.com/TakWolf/fusion-pixel-font/releases/tag/2026.10.25)
- 发布提交：`3266d59c25c3fa8f8b5e163b29736a706fd9ab6f`
- 原始压缩包：[fusion-pixel-font-12px-proportional-otf.woff2-v2026.10.25.zip](https://github.com/TakWolf/fusion-pixel-font/releases/download/2026.10.25/fusion-pixel-font-12px-proportional-otf.woff2-v2026.10.25.zip)
- 压缩包 SHA-256：`0501b4f770887eef5fc5ac94401b3b7bb38253ffed3a549e2cb0be89a0a03fe3`
- 字体：`fusion-pixel-12px-proportional-zh_hans.otf.woff2`（701,520 字节）
- 字体 SHA-256：`b67eb7aa592622e5bc1152b800d32404bb887a1e3a2e669b0c2a873d388590d6`

字体以 SIL Open Font License 1.1 发布，版权为原作者所有。随字体保留压缩包中的 [OFL.txt](./OFL.txt)，以及组合字形来源的 [Ark Pixel](./LICENSES/ark-pixel/OFL.txt)、[Cubic 11](./LICENSES/cubic-11/OFL.txt)、[Galmuri](./LICENSES/galmuri/LICENSE.txt) 声明。没有使用游戏原版字体或从参考项目复制字体。

`minecraft-theme.css` 声明 `Fusion Pixel SC`，仅在选中方块工坊时使用。保留 `font-display: swap` 的系统字体回退，并关闭合成粗体。代码块和数学公式沿用各自专用字体。Vite 构建会将本文、OFL 和 LICENSES 一并复制到 `dist/assets/fonts/fusion-pixel/`，与打包的 WOFF2 一起分发。
