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
    match = re.fullmatch(r"Output\s+for\s+(?:the\s+)?Sample\s+Input(?:\s*(\d+))?\s*[:：]?",
                         text, re.IGNORECASE)
    if match:
        return "output", int(match[1] or 1)
    match = re.fullmatch(r"(入力例|出力例)\s*(\d+)?\s*[:：]?", text)
    if match:
        return ("input" if match[1] == "入力例" else "output"), int(match[2] or 1)
    return None


def heading_blocks(root):
    """Keep each heading's body bounded by the next heading, including nested markup."""
    nodes = list(root.walk())
    headings = [position for position, node in enumerate(nodes) if node.tag in HEADING_TAGS]
    return [(nodes[start], nodes[start + 1:end])
            for start, end in zip(headings, headings[1:] + [len(nodes)])]


def block_text(nodes):
    # Read direct text once; calling text() on every ancestor would duplicate it.
    return " ".join(child for node in nodes if node.tag not in {"script", "style"}
                    for child in node.children if isinstance(child, str))


def sample_attachments(nodes, source_url):
    """Recognize public sample ZIP references; do not fetch or unpack external files."""
    attachments = {}
    verbatim = {id(child) for node in nodes if node.tag in {"pre", "code"} for child in node.walk()}
    for node in nodes:
        if id(node) in verbatim or node.tag != "a" or not node.attrs.get("href"):
            continue
        url = urljoin(source_url, node.attrs["href"])
        try:
            parts = urlsplit(url)
            valid = (parts.scheme == "https" and parts.hostname == "img.atcoder.jp"
                     and parts.port in (None, 443) and not parts.username and not parts.password
                     and parts.path.lower().endswith(".zip"))
        except ValueError:
            valid = False
        if valid:
            attachments.setdefault(url, {"url": url, "name": " ".join(node.text().split()) or "官方样例 ZIP"})
    return list(attachments.values())


def parse_samples(root, apg=False, source_url=""):
    blocks = heading_blocks(root)
    candidates = []
    answer_level = None
    no_input = False
    for position, (node, body) in enumerate(blocks):
        title = " ".join(node.text().split())
        heading = sample_heading(title)
        level = int(node.tag[1])
        numbered = bool(re.search(r"\d", title))
        if apg:
            if title in {"回答例", "解答例"}:
                answer_level = level
                continue
            if answer_level is not None:
                if level <= answer_level and (heading is None or numbered):
                    answer_level = None
                else:
                    continue
        if title.lower() in {"input", "入力"}:
            no_input = no_input or bool(re.fullmatch(
                r"(?:no input (?:is given|is provided)(?: for this problem)?|"
                r"this problem (?:provides|has|requires) no input|"
                r"there is no input in this problem|"
                r"(?:the )?input(?: given from standard input)? is empty|"
                r"(?:今回、|この問題に|この問題には|この問題では|標準入力から与えられる)?"
                r"入力は(?:ありません|ない|与えられない|与えられません|空である|空です))[.。．]?",
                " ".join(block_text(body).split()), re.IGNORECASE))
        if heading is not None:
            candidates.append((position, node, body, heading, numbered))
    if apg and candidates:
        # APG exercises repeat unnumbered examples inside the prose (h4/h5),
        # then publish their official numbered samples at a higher heading level.
        formal = [int(node.tag[1]) for _, node, _, _, numbered in candidates if numbered]
        if formal:
            level = min(formal)
            candidates = [entry for entry in candidates if entry[4] or int(entry[1].tag[1]) <= level]
    omission = re.compile(r"出力は[^。]*記載しません")
    omitted_output = any(heading[0] == "output" and omission.search(block_text(body))
                         for _, _, body, heading, _ in candidates)
    entries = []
    attachments_by_position = {}
    supplemental_inputs = {}
    for position, node, body, (kind, number), _ in candidates:
        pre = next((candidate for candidate in body if candidate.tag == "pre"), None)
        attachments = sample_attachments(body, source_url)
        if attachments:
            attachments_by_position[position] = attachments
        supplemental = "この入力は採点用テストケースに含まれません"
        verbatim = {id(child) for candidate in body if candidate.tag in {"pre", "code"}
                    for child in candidate.walk()}
        if kind == "input" and any(
                candidate.tag == "p"
                and id(candidate) not in verbatim
                and not any(child.tag in {"pre", "code"} for child in candidate.walk())
                and re.fullmatch(re.escape(supplemental) + r"[。．.]?", " ".join(candidate.text().split()))
                for candidate in body):
            supplemental_inputs[number] = supplemental + "。"
        note = None
        if pre is None:
            paragraphs = [candidate.text().strip() for candidate in body if candidate.tag == "p"]
            description = "\n".join(paragraph for paragraph in paragraphs if paragraph)
            # The omitted-output format explicitly declares the omission in its
            # first sample, then gives only optimal-cost descriptions afterwards.
            if attachments:
                note = f"样例{'输入' if kind == 'input' else '输出'}由官方 ZIP 附件提供，未展开为文本。"
                value = None
            elif (kind == "output" and omitted_output and description
                    and (omission.search(description) or re.search(r"最小のコスト", description))):
                note = description
                value = None
            else:
                raise ValueError(f"样例 {number} 的 {kind} 缺少 pre 内容")
        else:
            value = pre.text().replace("\r\n", "\n").replace("\r", "\n")
        entries.append((kind, number, value, note, position))

    if len(entries) > 2 and not any(entry[4] for entry in candidates):
        # Repeated unnumbered examples are only safe when the source explicitly
        # alternates adjacent input/output sections; never guess mixed numbering.
        if (len(entries) % 2 == 0
                and all(entry[0] == ("input" if i % 2 == 0 else "output")
                        for i, entry in enumerate(entries))
                and all(entries[i + 1][4] == entries[i][4] + 1 for i in range(0, len(entries), 2))):
            entries = [(kind, i // 2 + 1, value, note, position)
                       for i, (kind, _, value, note, position) in enumerate(entries)]
    outputs = [number for kind, number, *_ in entries if kind == "output"]
    inputs = [number for kind, number, *_ in entries if kind == "input"]
    count = len(inputs)
    if (len(outputs) != len(set(outputs)) and len(entries) == count * 2
            and inputs == list(range(1, count + 1))
            and all(entry[0] == ("input" if i % 2 == 0 else "output")
                    for i, entry in enumerate(entries))
            and all(entries[i + 1][4] == entries[i][4] + 1 for i in range(0, len(entries), 2))
            and all(1 <= number <= count for number in outputs)):
        # A few historical statements misnumber an output heading. Only recover
        # unambiguous adjacent pairs with consecutive, unique input numbers.
        entries = [(kind, entries[i - 1][1] if kind == "output" else number, value, note, position)
                   for i, (kind, number, value, note, position) in enumerate(entries)]
    samples = {}
    for kind, number, value, note, position in entries:
        pair = samples.setdefault(number, {"index": number})
        if kind in pair:
            raise ValueError(f"样例 {number} 的 {kind} 重复出现")
        pair[kind] = value
        if note:
            pair[kind + "_note"] = note
        for attachment in attachments_by_position.get(position, []):
            saved = pair.setdefault("attachments", [])
            if all(item["url"] != attachment["url"] for item in saved):
                saved.append(attachment)
    for number, pair in samples.items():
        if "input" not in pair and no_input:
            pair["input"] = ""
        if "output" not in pair and "input" in pair:
            if pair.get("attachments") and pair["input"] is None:
                pair.update(output=None, output_note="原站未在该样例章节提供文本输出，请参阅题面及附件。")
            elif number in supplemental_inputs:
                pair.update(output=None, output_note=supplemental_inputs[number])
        if "input" not in pair or "output" not in pair:
            raise ValueError(f"样例 {number} 的输入和输出不完整")
    result = [samples[number] for number in sorted(samples)]
    if 0 in samples:
        # Keep source numbering as metadata while retaining positive indices for
        # existing consumers and copy controls.
        for index, pair in enumerate(result, 1):
            pair["source_index"], pair["index"] = pair["index"], index
    return result


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
        ordered = ([preferred_language] if preferred_language in languages else [])
        ordered.extend(language for language in languages if language not in ordered)
        statements = [(language, languages[language]) for language in ordered]
    else:
        language = "ja" if re.search(r"問題文|入力例|出力例", task.text()) else "en"
        statements = [(language, task)]
    apg = bool(re.match(r"/contests/apg4b(?:python)?/tasks/", urlsplit(source_url).path, re.IGNORECASE))
    title = next((node.text().strip() for node in parser.root.walk()
                  if "h2" in (node.attrs.get("class") or "").split()), "")
    lesson = apg and bool(re.match(r"[A-Z]+\s*-\s*\d+\.\d+", title))
    preferred_error = None
    for language, statement in statements:
        try:
            plain = statement.text(blocks=True)
            plain = "\n".join(line.strip() for line in plain.splitlines())
            plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
            if not plain:
                raise ValueError("AtCoder 原站未提供题面正文（空题面，可能为系统测试或未公开题目）")
            # APG lessons contain independent exercises and demonstrations; retain
            # these in the statement rather than treating them as one judge's samples.
            samples = [] if lesson else parse_samples(statement, apg=apg, source_url=source_url)
            return {"statement_html": statement.inner_html(source_url).strip(),
                    "statement_text": plain, "statement_language": language, "samples": samples}
        except ValueError as error:
            # An official translation can contain a heading typo. Switch the
            # entire statement only if another language independently validates.
            if preferred_error is None:
                preferred_error = error
    raise preferred_error


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
    if raw.startswith(b"%PDF-"):
        if len(raw) > 20 * 1024 * 1024:
            raise ValueError("CF PDF 题面超过 20 MiB")
        if not re.match(rb"%PDF-(?:1\.\d|2\.0)\b", raw) or b"%%EOF" not in raw[-1024:]:
            raise ValueError("CF PDF 题面不完整或格式无效")
        # Keep the original document: extracting text would lose diagrams and sample layout.
        return {"statement_html": None, "statement_text": None, "statement_pdf": raw,
                "statement_language": "en", "samples": []}
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
        # Some legitimate problems (e.g. 171E) have an empty sample-test container.
        if not values["input"] and not values["output"]:
            if any(isinstance(child, Node) or child.strip() for child in group.children):
                raise ValueError("CF 样例区非空，但无法识别输入和输出")
            continue
        if len(values["input"]) != len(values["output"]):
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
