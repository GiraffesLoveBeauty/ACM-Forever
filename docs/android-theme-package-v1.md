# ACMforever 本地主题包 v1

状态：v0.2.17 / code31 本地实现，待跨人 review。用户要求：导出后导入应还原同一套主题与背景设置；图片不再次压缩、不降分辨率。主题包不上传后端，也不包含账号或服务地址。

## 使用入口

- 导入：个性化设置 → 主题选择 → **本地导入**，位于“主题库”下面。选择系统文档提供器中的 `.acmtheme` 文件。
- 导出：我的主题 → 对应主题“设置” → **导出**，位于“重命名”和“删除”之间。系统保存器决定目标位置。
- 导入成功只新增一套本机主题，不立即覆盖当前外观。点击主题名称或名称下的预览图应用；设置页修改仍只自动保存该主题。
- 网页配色 JSON 的旧导入入口继续位于主题库内，与本地完整主题包分开。

## 格式和体积

扩展名 `.acmtheme`，内容为标准 ZIP，MIME 为 `application/zip`。仅包含：

```text
example.acmtheme
├── theme.json       # UTF-8紧凑JSON，ZIP Deflate，最多64 KiB
└── background.bin   # 可选；导入相册时保留的原图字节，ZIP Store，最多20 MiB
```

不存缩略图、Base64、多余字体、其他主题或缓存。图片通常已压缩，用 ZIP Store 避免重复压缩的 CPU 开销；小配置使用 Deflate。包的主要大小就是原图本身，不能在保持原始字节的同时承诺把任意图片大幅变小。超限明确报错，不偷偷压缩。

配置结构：

```json
{
  "format": "acmforever.theme",
  "version": 1,
  "name": "我的主题",
  "settings": {
    "theme_source": "acm",
    "theme_primary": -3610335,
    "theme_secondary": -1,
    "theme_dark": false,
    "bg_mode": "image",
    "bg_source": "custom",
    "bg_crop": "[0.125,0.25,0.875,0.9]",
    "bg_transparency": 2,
    "module_transparency": 0,
    "control_transparency": 0
  },
  "background": {
    "path": "background.bin",
    "sizeBytes": 12345,
    "sha256": "原图的64位小写十六进制摘要；此处为示意"
  }
}
```

示例不是可直接导入的完整包，摘要和大小由实际原图生成。颜色使用 Android 有符号32位 ARGB 整数，往返不改颜色值。没有原图时省略 `background` 与对应文件；图片模式缺少原图则拒绝导入。

## 完整还原哪些设置

| 字段 | 语义 |
| --- | --- |
| `theme_source` | `acm` 或 `web` |
| `theme_preset`、`theme_dark` | 选用模板与浅/深模式；导入时模板内部ID可重新分配 |
| `theme_primary`、`theme_secondary` | ACMForever主/辅色 |
| `theme_custom_color`、`secondary_custom_color`、`background_custom_color` | 是否使用调色盘自定义颜色的布尔标记；实际颜色在主/辅/背景色字段中，避免界面选项丢失 |
| `bg_mode`、`bg_source`、`bg_color` | 纯色/渐变/图片，跟随主题/自定义及背景色 |
| `bg_crop` | 经 EXIF 方向处理后的归一化裁剪矩形 `[left,top,right,bottom]` |
| `bg_transparency` | 背景图透明度，0–5六档 |
| `module_transparency` | 模块背景透明度，0–5六档 |
| `control_transparency` | 按键、搜索栏和底部菜单背景透明度，0–5六档 |
| `webPreset` | 网页模板时额外保存选中模板的完整浅深配色、六类覆盖及设计ID |

`webPreset` 的 `theme` 复用现有网页 v1 配色 JSON，包括 `version/mode/light/dark`；每个 profile 包含 `primary/background/surface/accent` 和 `text/muted/border/link/selected/hero` 覆盖。`design_template` 限当前四套官方模板 `original/phase/angel-city/minecraft`。导入时保存这一份快照，不依赖将来官方默认配色；不会把整个网页收藏库塞进包。

内置“工业黄”有依赖预设ID的特殊默认色。`WebThemes.profile` 在解析浅/深两套配色时，将六类有效默认色固化为覆盖字段，保留已有显式覆盖；导出和离线主题层共用该解析结果。导入后即使ID重分配为 `portable-*`，仍保留相同原生配色，其中浅色横幅为 `#20231f`、深色为 `#151814`。这是格式v1内的完整快照，不需要新增ID特例或更改包版本。修复前已导出的包未保存这些信息，需要从原内置主题重新导出。

内部主题ID与 `bg_image_id` 重新生成，防止覆盖旧主题；这不改变实际外观。名称保留，允许两套同名主题，以独立ID管理。历史未显式保存的字段继续使用相同客户端默认值。跨越未来不兼容模板引擎时需要格式迁移或明确报错，本格式不承诺任意未来版本的像素完全一致。

## 原图与裁剪

从 v0.2.17 起，相册选择后的原图按字节复制到私有目录。自由裁剪仅保存归一化坐标，显示时按坐标取景；不再把缩小预览重新编码成 JPEG。原文件扩展名为历史内部路径，不代表对输入图片转码，格式以内容识别。

主题保存、应用、导出、导入均复制同一原图字节。预览可按屏幕进行采样以限制内存，存储文件与导出文件不受影响。图像中的 EXIF 方向和其他元数据也随原图保留；向他人分享前由用户决定是否另行处理照片元数据，App不隐式修改原图。

旧版已经转存的低分辨率 JPEG 无法恢复不存在的细节，重新从相册选原图后才适用新的原图保留流程。

## 校验与写入

只接受固定两个 ZIP 条目，拒绝重复条目、目录、路径穿越、额外脚本/文件；解压读取有实际字节上限，拒绝压缩炸弹。JSON字段白名单、版本、字段类型、颜色整数、六档透明度和裁剪范围均校验。原图按大小和 SHA256 核对，安装前确认是可识别图片。

完整读取校验后才创建随机ID、写原图和设置，最后登记到“我的主题”；失败清理未登记数据，既有主题与当前设置不被部分覆盖。导入与应用两步分开。密码、Cookie、CSRF、API地址、搜索历史、通知时间均不在格式白名单中。

对应代码：`ThemePackage` 负责格式与有界读写，`LocalThemes` 负责本机保存/安装，`ProfileCover` 负责原图和裁剪，`AppearanceActivity` 负责系统文档选择器。验证记录见 [v0.2.17](android-v0.2.17.md)。
