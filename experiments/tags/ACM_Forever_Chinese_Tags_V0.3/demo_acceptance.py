#!/usr/bin/env python3
"""生成离线验收页面；真实数据只读，修改及翻译仅在临时模拟目录执行。"""
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from label_pipeline import BASE, TAG_BY_ID, TAXONOMY
from problem_processing.adapter import normalize, read_problems
from problem_processing.backup import backup_root, checked_path, check_sensitive, verify_backup
from problem_processing.repository import PROJECT_ROOT, Repository
from problem_processing.translation import (language_plan, prepare_request, translate,
                                            current_translation)

GENERATED = BASE / "demo_generated"
TEMPLATE = BASE / "acceptance_demo_template.html"
STATUS = {"auto": "自动生效 · 未人工确认", "corrected": "人工修正 · 未完整确认",
          "verified": "人工完整确认", "needs_review": "异常 · 需要复核"}
ORIGINS = {"ai": "AI 候选", "cf_rule_mapping": "CF 规则映射",
           "manual_add": "人工添加", "legacy_human": "历史人工确认"}


def escaped(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def original_url(value, platform):
    """Only public OJ URLs without credentials, ports, fragments or query secrets."""
    try:
        url = urlsplit(value or "")
        hosts = {"atcoder": {"atcoder.jp", "www.atcoder.jp"},
                 "codeforces": {"codeforces.com", "www.codeforces.com"},
                 "nowcoder": {"ac.nowcoder.com", "www.nowcoder.com"}}
        if (url.scheme not in {"http", "https"} or url.hostname not in hosts.get(platform, set())
                or url.username or url.password or url.port or re.search(r"[\x00-\x20]", value)):
            return None
        return f"https://{url.hostname}{url.path}"
    except (TypeError, ValueError):
        return None


def git_information():
    def read(*args):
        result = subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True,
                                encoding="utf-8", errors="replace", check=False)
        return result.stdout.strip() if result.returncode == 0 else "未知"
    try:
        return {"branch": read("branch", "--show-current"), "commit": read("rev-parse", "HEAD"),
                "dirty": bool(read("status", "--porcelain"))}
    except OSError:
        return {"branch": "未知", "commit": "未知", "dirty": None}


def source_digest():
    """Bind test evidence to source/test/template bytes; never inspect .env or real datasets."""
    paths = list(BASE.glob("*.py")) + [TEMPLATE, BASE / "tag_taxonomy_v0.3.json", BASE / "cf_mapping_v0.3.json"]
    for folder in ("annotation_api", "problem_processing", "tag_management", "tests"):
        paths.extend((BASE / folder).rglob("*.py"))
    paths.extend((BASE / "tests/fixtures").glob("*.jsonl"))
    paths.extend((BASE / "tests/fixtures").glob("*.json"))
    paths.append(PROJECT_ROOT / "feat/api/acm_api/problem_content.py")
    digest = hashlib.sha256()
    for path in sorted(set(paths)):
        if path.is_file():
            digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode("utf-8") + b"\0" + path.read_bytes())
    return digest.hexdigest()


def load_live(root=None):
    repo = Repository(root)
    folder = repo.current()
    result = {"source": str(repo.root), "generation": None, "rows": [], "problems": 0,
              "auto_success": 0, "corrected": 0, "manual_events": 0,
              "real_translations": 0, "missing": folder is None}
    if folder is None:
        return result
    problems, automatic = repo.snapshot(folder)
    manager = repo.manager(folder)
    views = manager.get_effective_tags_many(sorted(problems))
    events, _ = manager.journal.read()
    index_path = repo.root / "translations/current.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    result.update(problems=len(problems), manual_events=len(events), generation=folder.name)
    for view in views:
        key = view["problem_key"]
        metadata, auto = problems[key], automatic[key]
        translation = current_translation(repo.root, metadata, index=index)
        result["real_translations"] += bool(translation and translation.get("translation_status") == "auto"
                                            and not str(translation.get("translation_model", "")).startswith("mock"))
        result["auto_success"] += auto.get("api_call_status") == "success" and not view["auto_tags"]["issues"]
        overrides = view["manual_overrides"]
        result["corrected"] += bool(overrides["added_tag_ids"] or overrides["removed_tag_ids"])
        links = [original_url(link, view["platform"]) for link in metadata.get("source_links", [])]
        ai = auto.get("ai_annotation") or {}
        # Explicit display allowlist: no statement, editorial, raw response or authentication fields.
        result["rows"].append({"problem_key": key, "platform": view["platform"],
            "source_problem_id": metadata.get("source_problem_id"),
            "title": metadata.get("original_title") or view.get("title") or "未提供题名",
            "auto_tags": view["auto_tags"]["tags"], "effective_tags": view["effective_tags"],
            "status": view["review_status"], "fully_human_verified": view["fully_human_verified"],
            "legacy_human_review_status": auto.get("human_review_status"),
            "raw_tags": metadata.get("raw_tags", []), "reason": ai.get("reason", "未保存判断依据"),
            "model": auto.get("model") or ai.get("model") or "未记录",
            "usage": {k: (auto.get("usage") or {}).get(k) for k in ("prompt_tokens", "completion_tokens", "total_tokens")},
            "content_hash": metadata.get("content_hash"), "call_status": auto.get("api_call_status"),
            "links": list(dict.fromkeys(link for link in links if link)),
            "added": overrides["added_tag_ids"], "removed": overrides["removed_tag_ids"],
            "issues": view["needs_review_reasons"]})
    return result


def load_processing_plan(root=None):
    from problem_processing.planning import Planner
    planner = Planner(root)
    plan = planner.plan(list(planner.problems.values()))
    return {"plan_id": plan["plan_id"], "summary": plan["summary"],
            "entries": [{"problem_key": row["problem_key"], "annotation": row["annotation"]["status"],
                         "translation": row["translation"]["status"], "needs_review": row["needs_human_review"]}
                        for row in plan["entries"]]}


def manual_demo():
    with tempfile.TemporaryDirectory(prefix="acm-acceptance-manual-") as tmp:
        problem = {"problem_key": "atcoder:offline:offline_demo", "platform": "atcoder",
                   "title": "模拟区间求和", "statement_markdown": "A synthetic static range sum problem.",
                   "statement_status": "ok"}
        metadata = normalize(problem)
        annotation = {**metadata["rule_base"], "model": "mock-only", "api_call_status": "success",
                      "specific_tag_ids": ["enumeration"], "provisional_tag_ids": []}
        repo = Repository(Path(tmp) / "labels")
        repo.import_records([problem], [annotation])
        manager = repo.manager()
        key = problem["problem_key"]
        steps = []
        for title, operation, tags in [("初始 AI 模拟标签", None, []),
                                        ("人工添加「前缀和」", "add", ["prefix_sum"]),
                                        ("人工删除「枚举」", "remove", ["enumeration"]),
                                        ("撤销全部覆盖，恢复自动标签", "reset", [])]:
            if operation:
                manager.change(key, operation, tags, actor="demo_only", reason="隔离验收演示")
            view = manager.get_effective_tags(key)
            steps.append({"title": title, "effective": view["effective_tags"],
                          "added": view["manual_overrides"]["added_tag_ids"],
                          "removed": view["manual_overrides"]["removed_tag_ids"],
                          "status": view["review_status"]})
        return {"steps": steps, "history_count": len(manager.history(key)), "isolated": True}


def translation_demo():
    result = []
    with tempfile.TemporaryDirectory(prefix="acm-acceptance-translation-") as tmp:
        for raw in read_problems(BASE / "tests/fixtures/translation_samples.jsonl"):
            problem = normalize(raw)
            plan = language_plan(problem)
            response = translate(problem, root=Path(tmp) / "labels", mock=True)
            prepared = prepare_request(problem, plan) if plan["action"] == "translate" else None
            protected = list(prepared["protected"].values()) if prepared else []
            translated = response.get("statement_zh")
            result.append({"title": problem["original_title"], "original": problem["original_statement"],
                           "language": plan["source_language"], "action": plan["action"],
                           "status": response["translation_status"], "translated": translated,
                           "protected_count": len(protected),
                           "protection_ok": all(piece in translated for piece in protected) if translated else None,
                           "real_api_calls": response.get("real_api_calls", 0)})
    return result


def backup_evidence(root, live_root):
    folder = backup_root(root)
    reports = []
    if not folder.is_dir():
        return {"source": str(folder), "reports": [], "missing": True}
    for path in sorted(folder.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        record = {"name": path.name, "path": str(path), "verified": False,
                  "restoration": "没有可核验的历史恢复记录"}
        try:
            verified = verify_backup(path)
            manifest = verified["manifest"]
            record.update(verified=True, created_at=manifest["created_at"],
                          files=manifest["file_count"], bytes=manifest["total_bytes"],
                          manifest_sha256=hashlib.sha256((path / "manifest.json").read_bytes()).hexdigest())
            # A historical claim is tied to these exact backup bytes, then independently rechecked.
            for audit_path in sorted((folder.parent / "audits").glob("*.json"), reverse=True):
                try:
                    audit = json.loads(audit_path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if not isinstance(audit, dict):
                    continue
                if (audit.get("manifest_sha256") != record["manifest_sha256"] or
                        Path(audit.get("backup", "")).resolve() != path.resolve()):
                    continue
                record.update(audit_source=str(audit_path), audit_date=audit.get("created_at"),
                              historical_equal=audit.get("all_ten_equal"))
                restored = audit.get("restored_data_root")
                if not restored or not Path(restored).is_dir():
                    record["restoration"] = "历史报告存在；隔离恢复目录已不可用，未冒充本次通过"
                    break
                active, isolated = Repository(live_root), Repository(checked_path(restored))
                before, after = active.snapshot()[0], isolated.snapshot()[0]
                keys = sorted(before)
                views_equal = (active.manager().get_effective_tags_many(keys) ==
                               isolated.manager().get_effective_tags_many(keys))
                history_equal = active.manager().journal.read() == isolated.manager().journal.read()
                equal = before == after and views_equal and history_equal
                record.update(restored_equal=equal, restored_count=len(keys), manual_history_equal=history_equal,
                              restoration=(f"本次只读复核：{len(keys)} 道题身份、内容哈希、状态、有效标签及人工历史一致"
                                           if equal else "隔离目录与当前数据存在差异，不能宣称一致"))
                break
        except (OSError, ValueError, KeyError, TypeError):
            record["error"] = "校验失败或记录不兼容；未执行恢复、未修改任何备份"
        reports.append(record)
    return {"source": str(folder), "reports": reports, "missing": not reports}


TEST_BOOTSTRAP = r'''
import json, socket, sys, time, unittest
from datetime import datetime, timezone
attempts = []
def deny(*args, **kwargs):
    attempts.append(1)
    raise AssertionError("Network forbidden in acceptance tests")
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
import httpx
httpx.HTTPTransport.handle_request = deny
suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
started = time.perf_counter()
result = unittest.TextTestRunner(verbosity=1).run(suite)
report = {"schema_version": 1, "executed_at": datetime.now(timezone.utc).isoformat(),
          "total": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
          "skipped": len(result.skipped), "expected_failures": len(result.expectedFailures),
          "unexpected_successes": len(result.unexpectedSuccesses),
          "seconds": round(time.perf_counter()-started, 3), "success": result.wasSuccessful(),
          "network_attempts": len(attempts), "real_api_calls": 0,
          "network_policy": "socket connections and real HTTP transport blocked"}
report["passed"] = (report["total"]-report["failures"]-report["errors"]-report["skipped"]
                    -report["expected_failures"]-report["unexpected_successes"])
print("ACM_ACCEPTANCE_TEST_REPORT=" + json.dumps(report))
sys.exit(0 if result.wasSuccessful() and not attempts else 1)
'''


def run_tests():
    result = subprocess.run([sys.executable, "-B", "-X", "utf8", "-c", TEST_BOOTSTRAP],
                            cwd=BASE, capture_output=True, text=True, encoding="utf-8", timeout=240)
    print(result.stderr, end="", file=sys.stderr)
    match = re.search(r"^ACM_ACCEPTANCE_TEST_REPORT=(.+)$", result.stdout, re.M)
    if not match:
        raise ValueError("测试进程未生成可核验摘要，未宣称测试通过")
    report = json.loads(match[1])
    report.update(source_digest=source_digest(), command="unittest discover -s tests -p test_*.py（网络阻断）",
                  process_exit=result.returncode, git=git_information())
    return report


def load_test_report(path):
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "executed_at", "total", "passed", "failures", "errors", "skipped",
                "seconds", "success", "real_api_calls", "source_digest", "network_attempts", "process_exit"}
    if not isinstance(value, dict) or not required <= value.keys() or value["schema_version"] != 1:
        raise ValueError("测试摘要格式不兼容")
    return {**value, "source": str(path), "matches_source": value["source_digest"] == source_digest()}


def tag_markup(tags):
    return "".join(f'<span class="tag {"provisional" if t["tag_kind"] == "provisional" else ""}" '
                   f'title="{escaped(t["id"])}">{escaped(t["name_zh"])}</span>' for t in tags) or '<span class="muted">空标签</span>'


def id_tags(values):
    return tag_markup([TAG_BY_ID[x] for x in values])


def render_page(data):
    check_sensitive(data)
    live, tests = data["live"], data["tests"]
    test_pass = bool(tests and tests["success"] and tests["matches_source"] and tests["process_exit"] == 0)
    metrics = [("标准算法词表", len(TAG_BY_ID), f'{TAXONOMY["specific_count"]} 个具体标签 · {TAXONOMY["provisional_count"]} 个临时大类'),
               ("已持久化题目", live["problems"], "读取当前目录版本，不读取实验预测输出"),
               ("自动标注成功", live["auto_success"], "自动结果可生效，仍不等于人工确认"),
               ("存在人工修正", live["corrected"], f'真实人工操作历史：{live["manual_events"]} 条'),
               ("当前真实译文", live["real_translations"], "只统计有效真实译文，Mock 不计入"),
               ("离线测试通过", f'{tests["passed"]}/{tests["total"]}' if tests else "未运行", "本次可核验源码" if test_pass else "见测试证据及源码匹配状态")]
    metric_html = "".join(f'<article class="metric"><span>{escaped(title)}</span><strong>{escaped(n)}</strong><small>{escaped(note)}</small></article>'
                          for title, n, note in metrics)
    rows, tag_options = [], {}
    for index, row in enumerate(live["rows"]):
        for tag in row["effective_tags"]:
            tag_options[tag["id"]] = tag["name_zh"]
        sources = list(dict.fromkeys(ORIGINS.get(t["source"], t["source"]) for t in row["effective_tags"]))
        links = " ".join(f'<a href="{escaped(link)}" target="_blank" rel="noopener noreferrer">原题 ↗</a>' for link in row["links"])
        detail_id = f"detail-{index}"
        state = row["status"]
        rows.append(f'''<tr class="problem-row" data-tags="{escaped(" ".join(t["id"] for t in row["effective_tags"]))}" data-status="{escaped(state)}" data-detail="{detail_id}">
          <td><span class="platform">{escaped(row["platform"])}</span><code>{escaped(row["problem_key"])}</code></td>
          <td><button class="problem-open" aria-expanded="false" aria-controls="{detail_id}">{escaped(row["title"])} <span>＋</span></button></td>
          <td>{tag_markup(row["auto_tags"])}</td><td>{tag_markup(row["effective_tags"])}</td>
          <td><span class="origin">{escaped(" / ".join(sources) or "无")}</span><span class="status {escaped(state)}">{escaped(STATUS.get(state, state))}</span></td><td>{links or "—"}</td></tr>
          <tr id="{detail_id}" class="detail-row" hidden><td colspan="6"><div class="detail-grid">
          <div><h4>标注依据 · AI 候选</h4><p class="reason">{escaped(row["reason"])}</p>
          <h4>最终有效标签与来源</h4>{"".join(f'<p>{escaped(t["name_zh"])} <code>{escaped(t["id"])}</code> · {escaped(" / ".join(ORIGINS.get(s, s) for s in t["sources"]))}</p>' for t in row["effective_tags"]) or "空标签"}</div>
          <div><h4>可追溯元数据</h4><dl><dt>原始来源 ID</dt><dd>{escaped(row["source_problem_id"])}</dd><dt>原始 OJ 标签</dt><dd>{escaped("、".join(row["raw_tags"]) or "无原生标签")}</dd>
          <dt>模型 / 调用状态</dt><dd>{escaped(row["model"])} / {escaped(row["call_status"])}</dd><dt>输入 / 输出 / 总 Token</dt><dd>{escaped(" / ".join(str(row["usage"].get(k, "未知")) for k in ("prompt_tokens", "completion_tokens", "total_tokens")))}</dd>
          <dt>内容哈希</dt><dd><code>{escaped(row["content_hash"])}</code></dd><dt>历史人工状态（原样兼容）</dt><dd>{escaped(row["legacy_human_review_status"])}</dd>
          <dt>人工新增 / 删除</dt><dd>{id_tags(row["added"])} / {id_tags(row["removed"])}</dd></dl></div></div></td></tr>''')
    manual = "".join(f'<article class="step"><span class="step-number">0{i+1}</span><h3>{escaped(step["title"])}</h3><div>{tag_markup(step["effective"])}</div><p>新增：{id_tags(step["added"])}<br>删除：{id_tags(step["removed"])}</p><small>{escaped(STATUS[step["status"]])}</small></article>'
                     for i, step in enumerate(data["manual"]["steps"]))
    translations = []
    for item in data["translations"]:
        translations.append(f'''<article class="translation"><div class="card-head"><h3>{escaped(item["title"])}</h3><span class="badge mock">Mock 演示</span></div>
        <p class="muted">语言：{escaped(item["language"])} · 操作：{escaped(item["action"])} · 状态：{escaped(item["status"])}</p>
        <div class="parallel"><div><h4>合成样本原文</h4><pre>{escaped(item["original"])}</pre></div><div><h4>Mock 响应实际返回的文本</h4><pre>{escaped(item["translated"] or "未生成译文：中文原文跳过翻译。")}</pre></div></div>
        <p class="protection">{f'公式、代码、变量等 {item["protected_count"]} 段原样保留：' + ('通过' if item['protection_ok'] else '未通过') if item["translated"] else '中文样本跳过，无新增译文'} · 真实 API 调用 0</p></article>''')
    backups = []
    for record in data["backups"]["reports"]:
        backups.append(f'''<article class="backup"><div class="card-head"><h3>{escaped(record["name"])}</h3><span class="badge {"good" if record["verified"] else "warn"}">{"SHA-256 校验通过" if record["verified"] else "校验失败"}</span></div>
        <dl><dt>备份创建时间</dt><dd>{escaped(record.get("created_at", "未知"))}</dd><dt>数据文件 / 数据量</dt><dd>{escaped(record.get("files", "未知"))} 个（不含 manifest） / {escaped(record.get("bytes", "未知"))} 字节</dd>
        <dt>manifest SHA-256</dt><dd><code>{escaped(record.get("manifest_sha256", "未确认"))}</code></dd><dt>隔离恢复一致性</dt><dd>{escaped(record["restoration"])}</dd>
        <dt>历史记录日期 / 来源</dt><dd>{escaped(record.get("audit_date", "未找到"))}<br>{escaped(record.get("audit_source", "无"))}</dd><dt>备份位置</dt><dd>{escaped(record["path"])}</dd></dl>
        <p class="muted">{escaped(record.get("error", "本次仅校验、查询既有隔离目录，没有执行恢复或替换活动数据。"))}</p></article>''')
    test_html = '<p class="empty">未找到本工具生成的测试摘要。请使用 --run-tests 实际运行，不沿用未经绑定的历史数字。</p>'
    if tests:
        test_html = f'''<div class="test-score"><strong>{escaped(tests["passed"])}</strong><span>通过 / {escaped(tests["total"])} 项</span><span class="badge {"good" if test_pass else "warn"}">{"全部通过 · 源码一致" if test_pass else "请检查测试结果或源码变化"}</span></div>
        <div class="test-facts"><span>失败 <b>{escaped(tests["failures"])}</b></span><span>错误 <b>{escaped(tests["errors"])}</b></span><span>跳过 <b>{escaped(tests["skipped"])}</b></span><span>耗时 <b>{escaped(tests["seconds"])} 秒</b></span><span>真实 API <b>{escaped(tests["real_api_calls"])}</b></span><span>网络尝试 <b>{escaped(tests["network_attempts"])}</b></span></div>
        <dl><dt>实际运行时间（UTC）</dt><dd>{escaped(tests["executed_at"])}</dd><dt>记录来源</dt><dd>{escaped(tests["source"])}</dd><dt>源码摘要匹配</dt><dd>{"匹配" if tests["matches_source"] else "不匹配：不能视为当前版本通过"}</dd></dl>'''
    planning = '<p class="empty">未生成本次离线计划；未推测需要调用的任务数量。</p>'
    if data.get("planning"):
        plan = data["planning"]
        summary = plan["summary"]
        labels = {"reuse_existing": "复用已有结果", "not_required": "无需 AI", "needs_annotation": "缺少标签",
                  "needs_translation": "缺少中文翻译", "needs_review": "待核验 · 阻断重发", "pending": "题面待处理", "invalid": "输入异常"}
        plan_rows = "".join(f'<tr><td><code>{escaped(r["problem_key"])}</code></td><td>{escaped(labels[r["annotation"]])}</td><td>{escaped(labels[r["translation"]])}</td></tr>'
                            for r in plan["entries"])
        planning = f'''<p>输入 → 统一适配 → 已有结果检查 → 独立标签 / 翻译计划 → 上方有效标签展示</p>
        <p>标签复用 / 无需 AI：<b>{escaped(summary["annotation_reused"])}</b> 题；待标注 <b>{escaped(summary["needs_annotation"])}</b> 题；
        待翻译 <b>{escaped(summary["needs_translation"])}</b> 题；待核验 <b>{escaped(summary["needs_review"])}</b> 题。
        预计 API 任务 <b>{escaped(summary["estimated_api_tasks"])}</b> 个，实际调用 <b>0</b>。</p>
        <div class="table-wrap"><table><thead><tr><th>题目身份</th><th>标签任务</th><th>翻译任务</th></tr></thead><tbody>{plan_rows}</tbody></table></div>
        <p class="source-note">只读当前持久版本及已有请求证据。计划 ID：<code>{escaped(plan["plan_id"])}</code><br>
        本页面不会执行计划。7G 已接入发送前重检、跨进程任务锁和未知结果阻断；仅通过离线 Mock 验证，尚不保证上游恰好计费一次。</p>'''
    values = {"GENERATED_AT": escaped(data["generated_at"]), "COMMIT": escaped(data["git"]["commit"]),
              "BRANCH": escaped(data["git"]["branch"]), "DIRTY": "工作区存在未提交更改" if data["git"]["dirty"] else "工作区干净",
              "METRICS": metric_html, "DATA_SOURCE": escaped(live["source"]), "GENERATION": escaped(live["generation"]),
              "PROBLEM_COUNT": str(len(live["rows"])), "PROBLEM_ROWS": "".join(rows),
              "DATA_WARNING": '<p class="notice">当前持久目录为空；页面未伪造题目或统计。</p>' if live["missing"] else "",
              "TAG_OPTIONS": "".join(f'<option value="{escaped(k)}">{escaped(v)}</option>' for k, v in sorted(tag_options.items(), key=lambda x:x[1])),
              "MANUAL_STEPS": manual, "MANUAL_HISTORY": str(data["manual"]["history_count"]),
              "TRANSLATIONS": "".join(translations), "BACKUPS": "".join(backups) or '<p class="empty">未找到备份目录或备份文件，未宣称备份成功。</p>',
              "TEST_RESULTS": test_html, "PROCESSING_PLAN": planning}
    return re.sub(r"@@([A-Z_]+)@@", lambda m: values[m[1]], TEMPLATE.read_text(encoding="utf-8"))


def write_generated(path, data):
    path = checked_path(path)
    if not path.is_relative_to(checked_path(GENERATED)) or path == GENERATED:
        raise ValueError("Demo 产物只能写入模块 demo_generated 目录")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".demo-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data.encode("utf-8"))
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", help="只读持久目录；默认现有 data/labels")
    parser.add_argument("--backup-root", help="只读备份目录；默认现有配置")
    parser.add_argument("--output", type=Path, default=GENERATED / "index.html")
    parser.add_argument("--run-tests", action="store_true", help="运行阻断网络的离线测试并保存实际摘要")
    args = parser.parse_args(argv)
    try:
        output = checked_path(args.output)
        if output.suffix.lower() != ".html" or not output.is_relative_to(checked_path(GENERATED)):
            raise ValueError("HTML 输出只能放在模块 demo_generated 目录")
        report_path = GENERATED / "test_report.json"
        if args.run_tests:
            report = run_tests()
            write_generated(report_path, json.dumps(report, ensure_ascii=False, indent=2))
        tests = load_test_report(report_path)
        live = load_live(args.data_root)
        data = {"live": live, "tests": tests, "manual": manual_demo(), "translations": translation_demo(),
                "planning": load_processing_plan(args.data_root),
                "backups": backup_evidence(args.backup_root, args.data_root), "git": git_information(),
                "generated_at": datetime.now(timezone.utc).isoformat()}
        write_generated(output, render_page(data))
        print(json.dumps({"html": str(output), "persistent_problems": live["problems"],
                          "auto_success": live["auto_success"], "real_translations": live["real_translations"],
                          "real_api_calls": 0, "tests": {k: tests[k] for k in ("total", "passed", "seconds", "matches_source")} if tests else None},
                         ensure_ascii=False, indent=2))
        return 1 if args.run_tests and (not tests["success"] or tests["process_exit"] != 0) else 0
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(f"Demo 生成失败（{type(exc).__name__}）；未输出敏感数据，请检查目录和数据完整性。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
