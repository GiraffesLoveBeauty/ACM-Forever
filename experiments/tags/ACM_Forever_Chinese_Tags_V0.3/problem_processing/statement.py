"""Conservative HTML-to-Markdown using the backend's existing parsing tree, offline."""
import importlib.util
import re
import sys
from functools import lru_cache
from urllib.parse import urljoin, urlsplit

from label_pipeline import BASE
from .markdown_text import escape_text


TEXT_MATH = re.compile(
    r'(?<![\\$])(?P<dollars>\${1,6})(?!\$)[\s\S]+?(?<!\\)(?P=dollars)(?!\$)'
    r'|(?<!\\)(?P<paren_slash>\\{1,2})\([\s\S]+?(?P=paren_slash)\)'
    r'|(?<!\\)(?P<bracket_slash>\\{1,2})\[[\s\S]+?(?P=bracket_slash)\]'
    r'|\\begin\{(?P<env>aligned|gathered|cases|[pbBvV]?matrix)\}[\s\S]+?\\end\{(?P=env)\}'
)


@lru_cache(maxsize=1)
def parser_module():
    path = BASE.parents[2] / "feat/api/acm_api/problem_content.py"
    name = "_acm_tag_statement_tree"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    # Execute the existing source without producing backend __pycache__ files.
    exec(compile(path.read_text(encoding="utf-8-sig"), str(path), "exec"), module.__dict__)
    return module


def newline(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def html_statement(raw, source_url="", language="en"):
    module = parser_module()
    mismatched, list_issues = [], []
    class CheckedTreeParser(module.TreeParser):
        def handle_starttag(self, tag, attrs):
            if tag in {'ol', 'li'}:
                names = [name for name, _ in attrs if name in {'start', 'value', 'type', 'reversed'}]
                if len(names) != len(set(names)):
                    list_issues.append('ambiguous_list_numbering')
            super().handle_starttag(tag, attrs)

        def handle_endtag(self, tag):
            if tag not in module.VOID_TAGS and self.stack[-1].tag != tag:
                mismatched.append(tag)
            super().handle_endtag(tag)
    parser = CheckedTreeParser()
    parser.feed(raw)
    parser.close()
    issues = list_issues + ([] if len(parser.stack) == 1 and not mismatched else ["unbalanced_html"])
    root = parser.root
    # Reuse known statement containers and language selectors, never include navigation.
    containers = [n for n in root.walk() if n.attrs.get("id") == "task-statement" or
                  "problem-statement" in (n.attrs.get("class") or "").split()]
    if containers:
        root = containers[0]
    elif any(n.tag in {"html", "body"} for n in root.walk()):
        issues.append("unknown_html_container")
    choices = [(lang, n) for n in root.walk() for lang in ("en", "ja")
               if "lang-" + lang in (n.attrs.get("class") or "").split()]
    if choices:
        language, root = next(((lang, n) for lang, n in choices if lang == language), choices[0])

    def link(value):
        url = urljoin(source_url or "", value or "")
        try:
            parsed = urlsplit(url)
            valid = (parsed.scheme in {"http", "https"} and parsed.hostname and not parsed.username
                     and not parsed.password and parsed.port is None and not re.search(r"[\x00-\x20()]", url))
        except ValueError:
            valid = False
        if not valid:
            issues.append("unsafe_or_unresolved_html_link")
            return None
        return url

    def list_integer(attrs, name, default):
        if name not in attrs:
            return default
        value = attrs[name]
        if isinstance(value, str) and re.fullmatch(r'[+-]?[0-9]+', value.strip()):
            try:
                number = int(value.strip())
                if -(2**31) <= number < 2**31:
                    return number
            except ValueError:
                pass
        issues.append('invalid_list_numbering')
        return default

    def render_list(node):
        ordered = node.tag == 'ol'
        items = [c for c in node.children if not isinstance(c, str) and c.tag == 'li']
        nested = [n for item in items for n in item.walk() if n.tag in {'ol', 'ul'}]
        if nested and (ordered or any(n.tag == 'ol' for n in nested)):
            # Literal markers preserve values, but not Markdown's nested list hierarchy.
            issues.append('nested_ordered_list_requires_review')
        if ordered and 'type' in node.attrs and node.attrs['type'] != '1':
            issues.append('unsupported_ordered_list_type')
        step = -1 if ordered and 'reversed' in node.attrs else 1
        number = list_integer(node.attrs, 'start', len(items) if step == -1 else 1) if ordered else None
        parts = []
        for child in node.children:
            if isinstance(child, str):
                if child.strip():
                    issues.append('invalid_list_structure')
                    parts.append(render(child))
            elif child.tag == 'li':
                if ordered:
                    if 'type' in child.attrs and child.attrs['type'] != '1':
                        issues.append('unsupported_ordered_list_type')
                    number = list_integer(child.attrs, 'value', number)
                    # Markdown engines renumber consecutive list items, ignoring li[value].
                    # Escaped dots keep the actual HTML counter as literal local structure.
                    marker = str(number) + r'\. '
                    number += step
                else:
                    marker = '- '
                parts.append(render(child, marker))
            else:
                if child.tag not in {'script', 'style'}:
                    issues.append('invalid_list_structure')
                parts.append(render(child))
        return '\n\n' + ''.join(parts).strip() + '\n\n'

    def prose(text):
        result, position = [], 0
        for match in TEXT_MATH.finditer(text):
            result.append(escape_text(re.sub(r'\s+', ' ', text[position:match.start()])))
            result.append(match[0])
            position = match.end()
        result.append(escape_text(re.sub(r'\s+', ' ', text[position:])))
        return ''.join(result)

    def render(node, item_marker=None, math_context=False):
        if isinstance(node, str):
            return re.sub(r'\s+', ' ', node) if math_context else prose(node)
        tag = node.tag
        if math_context:
            if tag not in {'var', 'span', 'sup', 'sub'}:
                issues.append('unsupported_math_markup')
            body = ''.join(render(c, math_context=True) for c in node.children)
            return ('^' if tag == 'sup' else '_') + '{' + body + '}' if tag in {'sup', 'sub'} else body
        if tag in {'ol', 'ul', 'li', 'style'} and re.search(
                r'list-style|counter(?:-reset|-increment|-set)?\s*:|display\s*:',
                node.attrs.get('style') or (''.join(c for c in node.children if isinstance(c, str)) if tag == 'style' else ''), re.I):
            issues.append('custom_list_numbering_requires_review')
        if any(name.lower().startswith(("mathjax", "katex")) for name in (node.attrs.get("class") or "").split()):
            issues.append("rendered_math_requires_review")
        if tag == "script":
            if str(node.attrs.get("type", "")).startswith("math/tex"):
                fence = "$$" if "mode=display" in node.attrs["type"].replace(" ", "") else "$"
                return fence + "".join(c for c in node.children if isinstance(c, str)) + fence
            return ""
        if tag in {"style", "noscript"}:
            return ""
        if tag in {"svg", "canvas", "iframe", "object", "embed", "math", "video", "audio", "form", "input", "button", "select"}:
            issues.append("unsupported_" + tag)
        if tag == "pre":
            # Same CF test-example-line convention as parse_codeforces().
            lines = [n for n in node.walk() if "test-example-line" in (n.attrs.get("class") or "").split()]
            text = "\n".join(n.text() for n in lines) + "\n" if lines else node.text()
            text = newline(text)
            fence = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", text)), default=0))
            return "\n\n" + fence + "\n" + text + ("" if text.endswith("\n") else "\n") + fence + "\n\n"
        if tag in {'ol', 'ul'}:
            return render_list(node)
        if tag == 'code':
            if any(n is not node and n.tag not in {'span', 'b', 'strong', 'em', 'i', 's', 'small', 'var', 'br'}
                   for n in node.walk()):
                issues.append('unsupported_code_markup')
            body = newline(node.text())
            if '\n' in body:
                issues.append('multiline_inline_code_requires_review')
            fence = '`' * max(1, 1 + max((len(x) for x in re.findall(r'`+', body)), default=0))
            padding = ' ' if body.startswith('`') or body.endswith('`') or (
                body.startswith(' ') and body.endswith(' ') and body.strip()) else ''
            return fence + padding + body + padding + fence
        if tag == 'var':
            return '$' + render(node, math_context=True) + '$'
        if tag in {'sup', 'sub'}:
            return render(node, math_context=True)
        body = "".join(render(c) for c in node.children)
        if tag == "img":
            issues.append("image_requires_review")
            url = link(node.attrs.get("src"))
            alt = escape_text(node.attrs.get('alt') or '图片')
            return f"![{alt}]({url})" if url else "[图片链接待检查]"
        if tag == "a":
            url = link(node.attrs.get("href"))
            return f"[{body}]({url})" if url else body
        if tag == "br":
            return "\n"
        if tag in {"strong", "b"}:
            return "**" + body + "**"
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            return "\n\n" + "#" * int(tag[1]) + " " + body.strip() + "\n\n"
        if tag in {"th", "td"}:
            if node.attrs.get("colspan", "1") != "1" or node.attrs.get("rowspan", "1") != "1":
                issues.append("complex_table")
            return " " + body.strip() + " |"
        if tag == "li":
            if item_marker is None:
                issues.append('orphan_list_item')
                item_marker = '- '
            boundary = '\n' if item_marker == '- ' else '\n\n'
            return boundary + (item_marker + body.strip()).rstrip() + boundary
        if tag in module.BLOCK_TAGS:
            return "\n\n" + ("|" if tag == "tr" else "") + body.strip("\n") + "\n\n"
        return body

    # Avoid whitespace cleanup inside fenced code/sample blocks.
    text = render(root).strip()
    if not text:
        issues.append("empty_html")
    if re.search(r"captcha|access denied|just a moment|sign in to continue", text, re.I):
        issues.append("possible_error_page")
    return {"text": text, "language": language, "issues": sorted(set(issues))}
