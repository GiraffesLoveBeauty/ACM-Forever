# 评论 Markdown

论坛根评论和回复支持 Markdown、链接、C++/Python/Java 等代码高亮、代码复制，以及 `$...$` / `$$...$$` 公式。编辑区可以切换预览；回复按钮返回编辑模式并聚焦输入框。提交失败保留原文，成功后清空，评论长度仍为 2–5000 个字符。

复用现有 Markdown 清洗、KaTeX 与代码复制能力，数据库仍保存源文，不保存浏览器生成的 HTML。本次没有增加评论图片上传或图片引用生命周期，评论中的图片显示为文字描述。旧评论直接按 Markdown 展示；需要保留 Markdown 特殊字符时可使用反斜杠转义或代码块。

本地验证使用 `pnpm build`、`pnpm test`，以及 `pnpm exec playwright test e2e/comment-markdown.spec.js`。浏览器测试使用临时合成数据库，覆盖预览、公式、高亮、复制、发布、回复、刷新持久化、HTML 清洗、失败保留和移动端溢出。
