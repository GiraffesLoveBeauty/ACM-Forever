# 帖子图片与缩略图

论坛卡片使用最长边 640 像素的 WebP 缩略图，并延迟加载。详情封面和正文继续使用原图；点击图片或按 Enter / 空格可放大查看，Escape 或「关闭图片」退出，焦点返回触发图片。加载失败时详情提供重试。正文中已有超链接的图片保持原有链接行为。

原图 API 保持 `/api/forum/images/<id>`，缩略图使用同一地址加 `?variant=thumb`。两者每次都校验发布状态和访问权限，均返回 `private, no-store`，帖子删除后缓存文件不能绕过访问限制。草稿、待审帖的私有图片不会因此公开。

缩略图在第一次授权访问时生成，保存到数据库旁的 `uploads/forum/thumbnails/`，使用临时文件和原子替换避免并发写入半张图片。删除该目录内的衍生文件后，下次访问会重新生成，不需要迁移数据库；原图文件必须保留。备份时可包含整个 `uploads/forum`。单张原图上传大小和账号存储限制保持不变。

验证命令：`pnpm test`、`pnpm build`（`feat/web` 下），以及仓库根目录的 `python -m unittest discover -s feat/api/tests -p "test_*.py"`。
