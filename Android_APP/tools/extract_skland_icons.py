"""Legacy vector decoder used only by build_reference_library.py.

The old app-resource extraction entry point has been disabled in v0.2.3.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile

ANDROID = "http://schemas.android.com/apk/res/android"
ET.register_namespace("android", ANDROID)
ICONS = {
    "comment": "icon_comment_scale",
    "forum": "icon_forum_scale",
    "rank": "icon_rank_scale",
    "search": "icon_search_scale",
    "filter": "icon_filter_20",
    "bookmark": "icon_collection_scale",
    "drafts": "post_svg_draft_icon",
    "add": "icon_add_scale",
    "article": "icon_post_article_scale",
    "calendar": "material_ic_calendar_black_24dp",
    "like": "icon_praise_scale",
    "comment_color": "notification_entry_comment",
    "eye": "design_ic_visibility",
    "eye_off": "design_ic_visibility_off",
    "avatar": "user_edit_avatar_placeholder_v2",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def decode(tree, table):
    stack = []
    root = None
    for line in tree.splitlines():
        element = re.match(r"( *)E: ([\w-]+)", line)
        if element:
            depth, tag = len(element[1]), element[2]
            while stack and stack[-1][0] >= depth:
                stack.pop()
            node = ET.Element(tag)
            if stack:
                stack[-1][1].append(node)
            else:
                root = node
            stack.append((depth, node))
            continue
        attr = re.match(r" *A: (?:http://schemas.android.com/apk/res/android:)?(\w+)(?:\(0x[0-9a-f]+\))?=(.*)", line)
        if not attr or not stack:
            continue
        name, value = attr.groups()
        if value.startswith('"'):
            value = value.split('"', 2)[1]
        else:
            value = value.split(" ", 1)[0]
        if value.startswith("@0x"):
            target = re.search(r"    resource " + re.escape(value[1:]) + r" [^\n]*\n\s+\([^)]*\) (.*)", table)
            if target:
                value = target[1].strip()
                if value.startswith('"'):
                    value = value.split('"', 2)[1]
                else:
                    value = value.split(" ", 1)[0]
        if value.startswith(("@", "?")):
            # Theme-dependent tint is supplied by this app. No path geometry changes.
            if name == "tint":
                continue
            if name in ("fillColor", "strokeColor"):
                value = "#FF1E211C"
            else:
                raise ValueError(f"Unresolved {name}={value}")
        enums = {"fillType": {"0": "nonZero", "1": "evenOdd"},
                 "strokeLineCap": {"0": "butt", "1": "round", "2": "square"},
                 "strokeLineJoin": {"0": "miter", "1": "round", "2": "bevel"}}
        if name in enums:
            value = enums[name].get(value, value)
        stack[-1][1].set("{" + ANDROID + "}" + name, value)
    if root is None or root.tag != "vector":
        raise ValueError("Expected a self-contained vector resource")
    ET.indent(root, space="    ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


if __name__ == "__main__":
    raise SystemExit("App extraction is disabled. Use build_reference_library.py --output <local-reference-directory>; app icons are original Canvas drawings.")
