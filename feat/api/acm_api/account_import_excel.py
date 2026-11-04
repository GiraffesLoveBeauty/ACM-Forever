"""Strict, bounded .xlsx I/O. Untrusted parsing runs only in the child worker."""
import io
import math
import re
import zipfile
from pathlib import PurePosixPath

TEMPLATE_VERSION = "account-import-v1"
COLUMNS = (
    ("QQ号", "qq_id", 12), ("昵称", "name", 64), ("姓名", "real_name", 64),
    ("身份", "status", 64), ("学校", "school", 128),
    ("Codeforces账号", "cf_handle", 64), ("洛谷UID", "luogu_id", 20),
    ("牛客UID", "nowcoder_id", 20), ("AtCoder账号", "atcoder_handle", 64),
    ("校OJ账号", "cjlu_username", 64),
)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 200
MAX_UNPACKED = 32 * 1024 * 1024
MAX_XML = 8 * 1024 * 1024
SHEETS = ("导入数据", "填写说明", "_meta")
MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ExcelError(Exception):
    def __init__(self, message, code="invalid_workbook"):
        super().__init__(message)
        self.code = code


def _text_cell(cell, value):
    cell.value = str(value if value is not None else "")
    cell.data_type = "s"
    cell.number_format = "@"
    cell.hyperlink = None


def template_bytes():
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    book = Workbook()
    data = book.active
    data.title = SHEETS[0]
    for i, (label, _, _) in enumerate(COLUMNS, 1):
        _text_cell(data.cell(1, i), label)
        data.cell(1, i).font = Font(bold=True, color="FFFFFF")
        data.cell(1, i).fill = PatternFill("solid", fgColor="315F4D")
        from openpyxl.utils import get_column_letter
        data.column_dimensions[get_column_letter(i)].width = 22 if i > 5 else 18
        for row in range(2, MAX_ROWS + 2):
            data.cell(row, i).number_format = "@"
    data.freeze_panes = "A2"
    instructions = book.create_sheet(SHEETS[1])
    lines = [
        "Excel 批量开户填写说明", "只填写导入数据工作表；不要修改表头或模板版本。",
        "QQ号必填，所有账号标识用文本格式；最多200行，5MiB。",
        "昵称可留空，新成员默认用QQ展示；姓名不会自动成为公开昵称。",
        "身份与Web权限无关；导入只创建普通成员。",
        "已有成员只补开户，表内其他资料全部忽略；已有/停用/注销账号不导入。",
        "OJ账号可留空；格式错误、重复或已占用时跳过绑定，不阻止合法QQ开户。",
        "五个平台都只填账号标识，不填网址、OJ密码、Cookie或Token。",
        "OJ录入需要管理员确认，不代表已通过本人归属验证；不会自动同步。",
        "新账号逐人生成随机初始密码，限时有效，首次登录必须修改。",
        "示例（合成，仅展示于说明页，请勿当作真实资料）：",
        "QQ号：10000084；昵称：导入示例；身份：现役；学校：示例学校",
        "Codeforces账号：ImportDemo84；洛谷UID：1000084；牛客UID：1000084；AtCoder账号：ImportDemo84；校OJ账号：demo84",
        "不支持公式、宏、外部链接、隐藏数据或额外工作表。",
    ]
    for i, line in enumerate(lines, 1):
        _text_cell(instructions.cell(i, 1), line)
        instructions.cell(i, 1).alignment = Alignment(wrap_text=True, vertical="top")
        instructions.row_dimensions[i].height = 34
    instructions.column_dimensions["A"].width = 110
    meta = book.create_sheet(SHEETS[2])
    _text_cell(meta.cell(1, 1), "template_version")
    _text_cell(meta.cell(1, 2), TEMPLATE_VERSION)
    meta.sheet_state = "hidden"
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def _inspect_zip(content):
    from defusedxml.ElementTree import fromstring
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        infos = archive.infolist()
        if len(infos) > 256:
            raise ExcelError("工作簿ZIP条目过多。", "resource_limit")
        seen, documents, unpacked = set(), {}, 0
        allowed = re.compile(r"(?:\[Content_Types\]\.xml|_rels/\.rels|docProps/(?:app|core|custom)\.xml|xl/(?:workbook\.xml|styles\.xml|sharedStrings\.xml|_rels/workbook\.xml\.rels|theme/theme1\.xml|worksheets/sheet[1-3]\.xml))")
        directories = {"_rels/", "docProps/", "xl/", "xl/_rels/", "xl/theme/", "xl/worksheets/"}
        for info in infos:
            name = info.filename
            if (name in seen or "\\" in name or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or (not allowed.fullmatch(name) and name not in directories) or info.flag_bits & 1):
                raise ExcelError("工作簿包含模板以外、重复或不安全的文件。")
            seen.add(name)
            with archive.open(info) as stream:
                raw = stream.read(MAX_XML + 1)
                if len(raw) > MAX_XML:
                    raise ExcelError("单个XML内容超过8MiB。", "resource_limit")
                unpacked += len(raw)
                if unpacked > MAX_UNPACKED:
                    raise ExcelError("解压后的内容超过32MiB。", "resource_limit")
            if name in directories:
                if raw:
                    raise ExcelError("工作簿目录不能包含文件内容。")
                continue
            tree = fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
            if name == "docProps/custom.xml":
                # Office/WPS bookkeeping is inert metadata, not executable workbook content.
                props_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/custom-properties}"
                value_ns = "{http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes}"
                primitives = {"lpwstr", "lpstr", "bstr", "i1", "i2", "i4", "i8", "int", "ui1", "ui2", "ui4", "ui8", "uint", "r4", "r8", "decimal", "bool", "filetime", "date"}
                if tree.tag != props_ns + "Properties":
                    raise ExcelError("自定义属性格式不支持。", "unsafe_content")
                for prop in tree:
                    if (prop.tag != props_ns + "property" or len(prop) != 1 or prop[0].tag not in {value_ns + kind for kind in primitives} or len(prop[0]) or "linkTarget" in prop.attrib):
                        raise ExcelError("只接受纯文本或数值的自定义属性。", "unsafe_content")
            count = 0
            for element in tree.iter():
                count += 1
                tag = element.tag.rsplit("}", 1)[-1]
                if count > 100_000 or (element.text and len(element.text) > 4096):
                    raise ExcelError("单元格或XML结构超过资源限制。", "resource_limit")
                if tag in {"f", "externalReference", "oleObject", "hyperlink", "definedName"}:
                    raise ExcelError("模板不接受公式、外部引用、定义名称或嵌入对象。", "unsafe_content")
                if tag == "Relationship":
                    target = element.attrib.get("Target", "")
                    reltype = element.attrib.get("Type", "").rsplit("/", 1)[-1]
                    custom = name == "_rels/.rels" and element.attrib.get("Type") == "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" and target == "docProps/custom.xml"
                    if element.attrib.get("TargetMode", "").lower() == "external" or (reltype not in {"officeDocument", "metadata/core-properties", "core-properties", "extended-properties", "worksheet", "styles", "theme", "sharedStrings"} and not custom) or ":" in target or "\\" in target or ".." in PurePosixPath(target).parts:
                        raise ExcelError("模板不接受外链或额外关系。", "unsafe_content")
                if tag == "Override" and ("macro" in element.attrib.get("ContentType", "").lower() or "vba" in element.attrib.get("ContentType", "").lower()):
                    raise ExcelError("不接受宏工作簿。", "unsafe_content")
            documents[name] = tree
        required = {"[Content_Types].xml", "xl/workbook.xml", "xl/_rels/workbook.xml.rels", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml"}
        if not required <= seen:
            raise ExcelError("文件不是完整的导入模板。")
        # Inspect actual cells independently of the dimension hint read_only trusts.
        for name, tree in documents.items():
            if not name.startswith("xl/worksheets/"):
                continue
            for element in tree.iter():
                tag = element.tag.rsplit("}", 1)[-1]
                if tag == "mergeCell":
                    raise ExcelError("模板不接受合并单元格。")
                if tag == "row" and (int(element.attrib.get("r", "0")) > 1000 or element.attrib.get("hidden") in {"1", "true"}):
                    raise ExcelError("模板不接受隐藏行或超出范围的行。", "resource_limit")
                if tag == "col" and (int(element.attrib.get("max", "0")) > 20 or element.attrib.get("hidden") in {"1", "true"}):
                    raise ExcelError("模板不接受隐藏列或额外列。")
                if tag == "c":
                    ref = element.attrib.get("r", "")
                    if not re.fullmatch(r"[A-T][1-9][0-9]{0,2}|[A-T]1000", ref):
                        raise ExcelError("单元格超出模板范围。", "resource_limit")
        return content
    except ExcelError:
        raise
    except Exception as exc:
        raise ExcelError("工作簿损坏或XML不安全，请重新下载模板。") from exc


def _identifier(cell, field):
    value = cell.value
    if value is None:
        return "", None
    if cell.data_type in {"f", "e", "d", "b"} or isinstance(value, bool) or cell.is_date:
        raise ValueError("账号不能是公式、错误、日期或布尔值")
    numeric = field in {"qq_id", "luogu_id", "nowcoder_id"}
    if isinstance(value, (int, float)):
        if not numeric or not math.isfinite(value) or value != int(value) or value < 0 or value >= 10**15:
            raise ValueError("账号标识请以文本填写，不能使用精度不确定的数字")
        return str(int(value)), "数字账号已转为精确整数文本；建议模板中按文本填写"
    if not isinstance(value, str):
        raise ValueError("请使用文本格式填写")
    return value.strip(), None


def parse_workbook(content):
    import os
    os.environ["OPENPYXL_LXML"] = "False"
    os.environ["OPENPYXL_DEFUSEDXML"] = "True"
    from openpyxl import load_workbook
    if not content or len(content) > MAX_FILE_BYTES:
        raise ExcelError("文件为空或超过5MiB。", "file_size")
    _inspect_zip(content)
    book = load_workbook(io.BytesIO(content), read_only=True, data_only=False, keep_links=False)
    try:
        if set(book.sheetnames) != set(SHEETS) or book[SHEETS[0]].sheet_state != "visible":
            raise ExcelError("请使用原模板的三个工作表，导入数据页必须可见。")
        meta = book["_meta"]
        meta.reset_dimensions()
        if meta["A1"].value != "template_version" or meta["B1"].value != TEMPLATE_VERSION:
            raise ExcelError("模板版本不支持，请重新下载。", "template_version")
        data = book[SHEETS[0]]
        data.reset_dimensions()
        raw_rows = data.iter_rows(max_col=20)
        header = next(raw_rows, ())
        if tuple(cell.value for cell in header[:10]) != tuple(col[0] for col in COLUMNS) or any(c.value is not None for c in header[10:]):
            raise ExcelError("模板表头缺失、重复或含未知列，请重新下载。", "invalid_headers")
        result = []
        for number, cells in enumerate(raw_rows, 2):
            if not any(cell.value is not None and str(cell.value).strip() for cell in cells):
                continue
            if len(result) >= MAX_ROWS:
                raise ExcelError("超过200行，请拆分表格。", "row_limit")
            if any(c.value is not None for c in cells[10:]):
                raise ExcelError("导入数据只能包含固定10列。", "invalid_headers")
            payload, errors, warnings = {}, [], []
            for (_, field, limit), cell in zip(COLUMNS, cells):
                try:
                    value, warning = _identifier(cell, field)
                    if len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
                        raise ValueError(f"字段长度上限{limit}，且不能含控制字符")
                    payload[field] = value
                    if warning:
                        warnings.append(warning)
                except ValueError as exc:
                    payload[field] = ""
                    label = dict((key, label) for label, key, _ in COLUMNS)[field]
                    if field in {key for _, key, _ in COLUMNS[5:]}:
                        warnings.append(f"{label}：已跳过绑定（{exc}）")
                    else:
                        errors.append(f"{label}：{exc}")
            result.append({"excel_row_number": number, "payload": payload, "errors": errors, "warnings": warnings})
        if not result:
            raise ExcelError("导入数据为空，请从第二行填写成员。", "empty_workbook")
        return result
    finally:
        book.close()


def report_bytes(rows):
    from openpyxl import Workbook
    book = Workbook()
    data = book.active
    data.title = "导入结果"
    headers = ["Excel行", "QQ号", "昵称", "动作", "结果", "错误", "提示", "忽略字段"]
    for i, label in enumerate(headers, 1):
        _text_cell(data.cell(1, i), label)
    for number, row in enumerate(rows, 2):
        values = [row["excel_row_number"], row["qq_id"], row.get("name", ""), row["action"], row["status"], "；".join(row["errors"]), "；".join(row["warnings"]), "、".join(row["ignored_fields"])]
        for i, value in enumerate(values, 1):
            _text_cell(data.cell(number, i), value)
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()
