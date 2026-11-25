"""Read-only Excel presentation of one assigned training and its fixed audience."""
import io
import re
from datetime import datetime, timedelta, timezone

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
SHANGHAI = timezone(timedelta(hours=8))
COMPLETIONS = {"on_time": "按时完成", "late": "逾期完成", "incomplete": "待完成",
               "not_started": "未开始", "timing_unknown": "时间待核验"}
ACCOUNT_STATES = {"active": "正常", "closed": "已注销", "changed": "账号已变更", "disabled": "已停用"}
PLATFORMS = {"codeforces": "Codeforces", "luogu": "洛谷", "atcoder": "AtCoder"}


def member_name(member):
    if member["account_status"] == "closed":
        return "已注销成员"
    if member["account_status"] == "changed":
        return "历史成员"
    return (member.get("real_name") or "").strip() or "未填写姓名"


def cell_label(cell):
    if cell.get("completed"):
        return "AC（历史）" if cell["platform"] == "luogu" else "AC（逾期）" if cell["status"] == "late" else "AC"
    return {"history_ac": "历史 AC（不计入）", "timing_unknown": "AC 时间待核验（不计入）",
            "not_started": "未开始", "unverified": "不支持核验"}.get(cell.get("status"), "未确认 AC")


def local_time(value):
    return datetime.fromtimestamp(value, SHANGHAI).strftime("%Y-%m-%d %H:%M:%S") if value else "—"


def workbook_bytes(task, members, *, now):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    workbook = Workbook()
    overview = workbook.active
    overview.title = "训练概况"
    matrix = workbook.create_sheet("成员进度")
    problems = workbook.create_sheet("题目列表")
    header_fill = PatternFill("solid", fgColor="27343A")
    ac_fill = PatternFill("solid", fgColor="A982FF")
    empty_fill = PatternFill("solid", fgColor="EDF0F2")
    pending_fill = PatternFill("solid", fgColor="FFF1C2")
    row_counts = {}

    def append(sheet, values):
        # Avoid rescanning every cell through max_row for each exported member.
        row = row_counts.get(sheet.title, 0) + 1
        row_counts[sheet.title] = row
        for column, value in enumerate(values, 1):
            cell = sheet.cell(row, column)
            if isinstance(value, str):
                # Force literal text, including =/+/-/@ prefixes. Strip invalid XML controls.
                cell.value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)[:32767]
                cell.data_type = "s"
                cell.number_format = "@"
            else:
                cell.value = value
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        return row

    def style_header(sheet):
        for cell in sheet[1]:
            cell.fill = header_fill
            cell.font = Font(bold=True, color="FFFFFF")
        sheet.row_dimensions[1].height = 36
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

    append(overview, ["项目", "内容"])
    for label, value in [
        ("训练 ID", task["id"]), ("训练标题", task["title"]), ("训练说明", task["description"]),
        ("任务状态", {"published": "已发布", "cancelled": "已取消"}.get(task["state"], task["state"])),
        ("开始时间（北京时间）", local_time(task["starts_at"])),
        ("截止时间（北京时间）", local_time(task["due_at"])),
        ("导出时间（北京时间）", local_time(now)),
        ("CF 完成规则", "历史 AC 可计入" if task["rule"] == "historical_ac" else "周期内 AC"),
        ("洛谷完成规则", "公开 P 题按历史 AC 计入，不判断完成时段，实际 AC 时间未知。"),
        ("固定接收人数", len(members)), ("题目数量", len(task["problems"])),
        ("已完成成员题目数", sum(m["completed_problems"] for m in members)),
        ("导出范围", "本次训练全部成员，不受页面筛选、分页影响；使用导出时已有本地证据，不触发外部同步。"),
        ("格子说明", "题目列按发布题单顺序排列；紫色为计入完成的 AC，灰色为未确认完成，黄色为无法核验或时间待核验。"),
        ("核验说明", "完成与核验独立；已确认的 AC 在同步失败、账号停用或注销后保留。历史 AC 不符合 CF 周期规则时不计入。"),
    ]:
        append(overview, [label, value])
    overview.column_dimensions["A"].width = 28
    overview.column_dimensions["B"].width = 100
    style_header(overview)

    completions = {**COMPLETIONS}
    if all(problem["platform"] == "luogu" for problem in task["problems"]):
        completions["on_time"] = "已完成"
    fixed_headers = ["姓名", "发布时昵称", "QQ号", "发布时身份", "已完成题数", "总题数", "完成状态", "账号状态", "待核验"]
    append(matrix, fixed_headers + [f'{index}. {PLATFORMS.get(p["platform"], p["platform"])} / {p["problem_id"]}\n{p["problem_name"]}'
                                   for index, p in enumerate(task["problems"], 1)])
    for member in members:
        by_id = {cell["id"]: cell for cell in member["problem_cells"]}
        cells = [by_id.get(p["id"], {}) for p in task["problems"]]
        row = append(matrix, [member_name(member), member["name"], str(member.get("qq_id") or ""), member["status_snapshot"],
                              member["completed_problems"], member["problem_count"], completions.get(member["completion"], member["completion"]),
                              ACCOUNT_STATES.get(member["account_status"], member["account_status"]), "是" if member["pending"] else "否"]
                             + [cell_label(cell) for cell in cells])
        for column, result in enumerate(cells, len(fixed_headers) + 1):
            cell = matrix.cell(row, column)
            cell.fill = ac_fill if result.get("completed") else pending_fill if result.get("status") in {"timing_unknown", "unverified"} else empty_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    style_header(matrix)
    matrix.freeze_panes = "E2"
    for index in range(1, matrix.max_column + 1):
        matrix.column_dimensions[get_column_letter(index)].width = 26 if index <= 4 else 22 if index > len(fixed_headers) else 14
    matrix.row_dimensions[1].height = 54

    append(problems, ["题目顺序", "平台", "题号", "题目名称", "难度", "原题链接"])
    for index, problem in enumerate(task["problems"], 1):
        append(problems, [index, PLATFORMS.get(problem["platform"], problem["platform"]), problem["problem_id"],
                          problem["problem_name"], problem.get("problem_rating") or "—", problem.get("problem_url", "")])
    style_header(problems)
    for column, width in zip("ABCDEF", (12, 18, 22, 60, 16, 75)):
        problems.column_dimensions[column].width = width
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()
