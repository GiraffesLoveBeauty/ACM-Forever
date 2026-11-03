# Markdown 代码块

帖子正文、投稿进度、管理员审核、Wiki 阅读及 Markdown 编辑器预览共用代码块高亮与复制功能。

## 指定代码语言

在三个反引号后填写语言，例如：

````markdown
```cpp
#include <iostream>
int main() {
    std::cout << "Hello, ACM!";
    return 0;
}
```

```python
def solve(n):
    return "AC" * n
```

```java
public class Main {
    public static void main(String[] args) {
        System.out.println("Hello, ACM!");
    }
}
```
````

| 语言 | 支持的标记（不区分大小写） |
| --- | --- |
| C++ | `cpp`、`c++`、`cc`、`cxx` |
| Python | `python`、`py`、`python3`、`py3` |
| Java | `java` |

未指定语言或使用其他标记时保留纯文本展示与复制，不自动猜测语言。行内代码不添加复制工具栏。

## 显示与复制

- 代码块固定使用纯黑背景和适配深色背景的语法颜色，在浅色、深色及自定义主题中保持一致。
- 代码使用独立的等宽字体栈，优先使用本机 Cascadia Code / Cascadia Mono、SFMono-Regular、Consolas 等字体；不跟随页面的像素字体。实际字体取决于设备上已安装的字体。
- 长行在代码区域内横向滚动，语言标签和复制按钮保留在工具栏内；Tab 显示宽度为 4 个空格。
- 点击“复制代码”复制原始代码，保留缩进、换行及特殊字符，不包含语言标签、按钮文字或高亮标签。
- 优先使用 Clipboard API；不可用或被拒绝时，尝试浏览器原生复制回退。全部失败时显示手动复制提示，并可重试。
- Wiki 中相邻的不同语言代码块仍可通过原有语言按钮切换。

高亮由本地打包的 highlight.js 提供，仅载入上述三种语言，不依赖 CDN。Markdown 先经过现有净化流程，再对代码文本生成高亮；图片允许列表及公式渲染沿用现有逻辑。

## 验证

在 `feat/web` 运行 `pnpm test` 和 `pnpm build`。`tests/markdown-code.test.mjs` 覆盖两种 Markdown 渲染路径、语言别名、HTML 字面量、复制回退及失败重试、预览更新和 Wiki 语言切换。

`pnpm test:e2e` 使用临时数据库，在桌面和手机浏览器验证真实剪贴板复制、主题下的代码样式、编辑预览及长行横向滚动。运行环境见 [前端说明](../feat/web/README.md)。
