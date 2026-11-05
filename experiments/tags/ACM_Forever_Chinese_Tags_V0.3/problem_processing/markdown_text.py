"""Serialize literal prose without creating Markdown, HTML or TeX delimiters."""
import html
import re


def escape_text(text):
    text = html.escape(text, quote=False)
    # The statement renderer recognizes TeX before Markdown escapes. Entities keep
    # literal brackets, dollar signs and backslashes out of that earlier pass too.
    text = re.sub(r'[\\$\[\]()`*_{}#!|~+\-]',
                  lambda m: f'&#{ord(m[0])};' if m[0] in '\\$[]()' else '\\' + m[0], text)
    # GFM autolinks otherwise absorb adjacent character references into the URL.
    text = re.sub(r'\b(https?)://', r'\1&#58;//', text, flags=re.I)
    # A text node may start after an inline wrapper containing a list number.
    return re.sub(r'(^[ \t]*[0-9]+|^)\.(?=[ \t]|$)', r'\1\\.', text)
