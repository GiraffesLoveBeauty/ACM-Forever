"""Parse public AtCoder and Codeforces statements and samples without extra packages."""

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK_TAGS = {"div", "section", "p", "pre", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "table", "tr"}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()

    def text(self, blocks=False):
        if self.tag in {"script", "style"}:
            return ""
        if self.tag == "br":
            return "\n"
        value = "".join(child.text(blocks) if isinstance(child, Node) else child for child in self.children)
        return "\n" + value + "\n" if blocks and self.tag in BLOCK_TAGS else value

    def render(self, source_url):
        if self.tag in {"script", "style"}:
            return ""
        attrs = []
        for key, value in self.attrs.items():
            if value is None:
                attrs.append(key)
            else:
                if key in {"src", "href"}:
                    value = urljoin(source_url, value)
                attrs.append(f'{key}="{html.escape(value, quote=True)}"')
        opening = "<" + self.tag + (" " + " ".join(attrs) if attrs else "") + ">"
        if self.tag in VOID_TAGS:
            return opening
        body = self.inner_html(source_url)
        return opening + body + "</" + self.tag + ">"

    def inner_html(self, source_url):
        return "".join(child.render(source_url) if isinstance(child, Node) else html.escape(child, quote=False)
                       for child in self.children)


class TreeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("document")
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in VOID_TAGS:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        # HTML ignores one newline immediately after an opening <pre> tag.
        if self.stack[-1].tag == "pre" and not self.stack[-1].children:
            if data.startswith("\r\n"):
                data = data[2:]
            elif data.startswith(("\r", "\n")):
                data = data[1:]
        self.stack[-1].children.append(data)


def sample_heading(text):
    text = " ".join(text.split())
    match = re.fullmatch(r"Sample\s+(Input|Output)(?:\s*(\d+))?\s*[:：]?", text, re.IGNORECASE)
    if match:
        return match[1].lower(), int(match[2] or 1)
    match = re.fullmatch(r"(入力例|出力例)\s*(\d+)?\s*[:：]?", text)
    if match:
        return ("input" if match[1] == "入力例" else "output"), int(match[2] or 1)
    return None


def parse_samples(root):
    nodes = list(root.walk())
    samples = {}
    for position, node in enumerate(nodes):
        heading = sample_heading(node.text()) if node.tag in HEADING_TAGS else None
        if heading is None:
            continue
        kind, number = heading
        if number < 1:
            raise ValueError("样例编号必须为正整数")
        pre = None
        for candidate in nodes[position + 1:]:
            if candidate.tag in HEADING_TAGS:
                break
            if candidate.tag == "pre":
                pre = candidate
                break
        if pre is None:
            raise ValueError(f"样例 {number} 的 {kind} 缺少 pre 内容")
        pair = samples.setdefault(number, {"index": number})
        if kind in pair:
            raise ValueError(f"样例 {number} 的 {kind} 重复出现")
        pair[kind] = pre.text().replace("\r\n", "\n").replace("\r", "\n")
    for number, pair in samples.items():
        if "input" not in pair or "output" not in pair:
            raise ValueError(f"样例 {number} 的输入和输出不完整")
    return [samples[number] for number in sorted(samples)]


def parse_atcoder(raw, source_url, preferred_language="en"):
    parser = TreeParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    task = next((node for node in parser.root.walk() if node.attrs.get("id") == "task-statement"), None)
    if task is None:
        raise ValueError("页面没有 task-statement，可能是登录页、错误页或未公开题目")
    languages = {}
    for node in task.walk():
        classes = (node.attrs.get("class") or "").split()
        for language in ("en", "ja"):
            if "lang-" + language in classes and node.text().strip():
                languages.setdefault(language, node)
    if languages:
        language = preferred_language if preferred_language in languages else next(iter(languages))
        statement = languages[language]
    else:
        statement = task
        language = "ja" if re.search(r"問題文|入力例|出力例", task.text()) else "en"
    plain = statement.text(blocks=True)
    plain = "\n".join(line.strip() for line in plain.splitlines())
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    if not plain:
        raise ValueError("题面内容为空")
    return {
        "statement_html": statement.inner_html(source_url).strip(),
        "statement_text": plain,
        "statement_language": language,
        "samples": parse_samples(statement),
    }


def parse_atcoder_tasks(raw, contest_id):
    parser = TreeParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    items = []
    seen = set()
    prefix = f"/contests/{contest_id}/tasks/"
    for row in parser.root.walk():
        if row.tag != "tr":
            continue
        links = []
        for node in row.walk():
            if node.tag != "a":
                continue
            url = urlsplit(urljoin("https://atcoder.jp", node.attrs.get("href") or ""))
            if url.hostname != "atcoder.jp" or not url.path.startswith(prefix):
                continue
            problem_id = url.path[len(prefix):]
            if re.fullmatch(r"[A-Za-z0-9_-]{1,100}", problem_id):
                links.append((problem_id, " ".join(node.text().split())))
        if not links or links[0][0] in seen:
            continue
        problem_id = links[0][0]
        title = next((text for key, text in reversed(links) if key == problem_id and text), "")
        if not title:
            raise ValueError(f"{problem_id} 缺少题名")
        items.append({
            "platform": "atcoder", "problem_id": problem_id, "contest_id": contest_id,
            "problem_index": links[0][1], "problem_name": title,
            "problem_rating": None, "tags": [],
            "problem_url": "https://atcoder.jp" + prefix + problem_id,
        })
        seen.add(problem_id)
    if not items:
        raise ValueError("没有公开的题目列表，比赛可能不存在、尚未开放或需要登录")
    return items


def parse_codeforces(raw, source_url):
    parser = TreeParser()
    parser.feed(raw.decode("utf-8-sig"))
    parser.close()
    statement = next((node for node in parser.root.walk()
                      if "problem-statement" in (node.attrs.get("class") or "").split()), None)
    if statement is None:
        raise ValueError("页面没有 problem-statement，可能是登录页、访问限制页或题目未公开")
    samples = []
    for group in statement.walk():
        if "sample-test" not in (group.attrs.get("class") or "").split():
            continue
        values = {"input": [], "output": []}
        for section in group.walk():
            classes = (section.attrs.get("class") or "").split()
            kind = next((key for key in values if key in classes), None)
            if not kind:
                continue
            pre = next((node for node in section.walk() if node.tag == "pre"), None)
            if pre is None:
                raise ValueError(f"CF 样例的 {kind} 缺少 pre 内容")
            lines = [node for node in pre.walk()
                     if "test-example-line" in (node.attrs.get("class") or "").split()]
            text = "\n".join(node.text() for node in lines) + "\n" if lines else pre.text()
            values[kind].append(text.replace("\r\n", "\n").replace("\r", "\n"))
        if not values["input"] or len(values["input"]) != len(values["output"]):
            raise ValueError("CF 样例的输入和输出不完整")
        for sample_input, sample_output in zip(values["input"], values["output"]):
            samples.append({"index": len(samples) + 1, "input": sample_input, "output": sample_output})
    plain = statement.text(blocks=True)
    plain = "\n".join(line.strip() for line in plain.splitlines())
    plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
    if not plain:
        raise ValueError("CF 题面内容为空")
    return {"statement_html": statement.inner_html(source_url).strip(), "statement_text": plain,
            "statement_language": "en", "samples": samples}
