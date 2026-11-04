"""Offline planning contracts, synthetic repositories/cache and read-only legacy integration."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import plan_processing
from annotation_api.adapter import adapt, digest
from label_pipeline import TAXONOMY
from problem_processing.adapter import normalize
from problem_processing.planning import Planner, semantic_inputs, task_policies, write_plan
from problem_processing.repository import Repository
from problem_processing.translation import TRANSLATION_VERSION, language_plan


def raw(number=0, **values):
    return {"problem_key": f"atcoder:offline:offline_{number}", "platform": "atcoder", "title": "Mock Addition",
            "statement_markdown": "You are given two integers. Print their sum.", "statement_status": "ok", **values}


def annotation(source, **values):
    p = normalize(source)
    return {**p["rule_base"], "taxonomy_version": TAXONOMY["version"], "specific_tag_ids": ["enumeration"],
            "provisional_tag_ids": [], "api_call_status": "success", "model": "offline-model",
            "annotation_input_hash": adapt(p)["annotation_input_hash"],
            "processing_policy": task_policies()["annotation"], **values}


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


class ProcessingPlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-plan-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = Repository(self.base / "labels")
        self.cache = self.base / "cache"
        for name in ("annotation_api.client.APIClient", "socket.create_connection"):
            guard = patch(name, side_effect=AssertionError("No real API in planner"))
            guard.start()
            self.addCleanup(guard.stop)

    def planner(self, **values):
        return Planner(self.repo.root, cache_roots=[self.cache], manifest_roots=[], **values)

    def seed(self, source=None, **values):
        source = source or raw()
        self.repo.import_records([source], [annotation(source, **values)])
        return source

    def entry(self, source=None, **values):
        return self.planner(**values).plan([source or raw()])["entries"][0]

    def translation(self, source=None, **values):
        p = normalize(source or raw())
        fp = digest({"translation": p["problem_key"]})
        row = {"problem_key": p["problem_key"], "source_content_hash": p["content_hash"],
               "source_verified_hash": p["verified_content_hash"], "request_fingerprint": fp,
               "translation_status": "auto", "translation_model": "offline-model", "translation_version": TRANSLATION_VERSION,
               "processing_policy": task_policies()["translation"], "title_zh": "模拟题名", "statement_zh": "模拟中文正文。", **values}
        save(self.repo.root / "translations/current.json", {p["problem_key"]: fp})
        save(self.repo.root / "translations/history" / (fp + ".json"), row)
        return row

    def cached(self, source=None, **values):
        row = annotation(source or raw(), **values)
        save(self.cache / "namespace" / (digest(row) + ".json"), {"state": "success", "merged": row})

    def test_both_missing_are_independent_tasks(self):
        p = self.planner().plan([raw()])
        self.assertEqual(p["entries"][0]["status"], "needs_both")
        self.assertEqual(p["summary"]["estimated_api_tasks"], 2)

    def test_persisted_labels_only_need_translation(self):
        self.seed()
        e = self.entry()
        self.assertEqual(e["status"], "needs_translation")
        self.assertFalse(e["annotation"]["needs_ai"])

    def test_existing_both_results_are_reused(self):
        self.seed(); self.translation()
        e = self.entry()
        self.assertEqual(e["status"], "reuse_existing")
        self.assertFalse(e["needs_ai"])

    def test_only_annotation_missing_with_translation_present(self):
        self.repo.import_records([raw()])
        self.translation()
        e = self.entry()
        self.assertEqual(e["status"], "needs_annotation")
        self.assertEqual(e["translation"]["status"], "reuse_existing")

    def test_chinese_source_does_not_need_translation(self):
        e = self.entry(raw(statement_markdown="给定两个整数，请计算它们相加的结果并输出。"))
        self.assertEqual(e["status"], "needs_annotation")
        self.assertEqual(e["translation"]["status"], "not_required")

    def test_cf_exact_mapping_requires_no_ai(self):
        source = {"platform": "codeforces", "problem_key": "codeforces:123:A", "raw_tags": ["dsu"],
                  "title": "模拟合并", "statement_markdown": "给定集合，请执行所有合并操作并输出答案。"}
        e = self.entry(source)
        self.assertEqual(e["status"], "reuse_existing")
        self.assertEqual(e["effective_tags"][0]["id"], "dsu")

    def test_manual_add_and_remove_take_priority(self):
        self.seed()
        manager = self.repo.manager()
        manager.change(raw()["problem_key"], "remove", ["enumeration"])
        manager.change(raw()["problem_key"], "add", ["prefix_sum"])
        e = self.entry()
        self.assertEqual([t["id"] for t in e["effective_tags"]], ["prefix_sum"])
        self.assertEqual(e["label_review_status"], "corrected")
        self.assertEqual(e["annotation"]["status"], "reuse_existing")

    def test_manual_tombstone_survives_new_auto_result(self):
        self.seed()
        self.repo.manager().change(raw()["problem_key"], "remove", ["enumeration"])
        self.seed(specific_tag_ids=["enumeration", "prefix_sum"])
        self.assertEqual([t["id"] for t in self.entry()["effective_tags"]], ["prefix_sum"])

    def test_content_change_marks_both_results_for_review(self):
        self.seed(); self.translation()
        e = self.entry(raw(statement_markdown="You are given three integers. Print their product."))
        self.assertEqual([e[t]["status"] for t in ("annotation", "translation")], ["needs_review", "needs_review"])
        self.assertFalse(e["needs_ai"])

    def test_same_reported_hash_cannot_hide_changed_statement(self):
        self.seed(raw(content_hash="fixed"))
        e = self.entry(raw(content_hash="fixed", statement_markdown="You are given three different numbers."))
        self.assertEqual(e["annotation"]["status"], "needs_review")

    def test_irrelevant_metadata_changes_keep_task_keys(self):
        self.seed()
        a = self.entry()
        b = self.entry(raw(difficulty=999, fetched_at="2030-01-01", source_links=["https://atcoder.jp/"],
                           adapter_source_path="D:/different/code.py", output_path="E:/other/output"))
        for task in ("annotation", "translation"):
            self.assertEqual(a[task]["task_key"], b[task]["task_key"])
            self.assertEqual(a[task]["status"], b[task]["status"])

    def test_external_content_hash_change_alone_does_not_rerun(self):
        self.seed()
        self.assertEqual(self.entry(raw(content_hash="different-external-hash"))["annotation"]["status"], "reuse_existing")

    def test_raw_tag_change_affects_annotation_only(self):
        self.seed(); self.translation()
        e = self.entry(raw(raw_tags=["new-hint"]))
        self.assertEqual(e["annotation"]["status"], "needs_review")
        self.assertEqual(e["translation"]["status"], "reuse_existing")

    def test_translation_prompt_revision_does_not_invalidate_labels(self):
        self.seed(); self.translation()
        a = self.entry()
        b = self.entry(policies=task_policies(translation_revision=TRANSLATION_VERSION + "-changed"))
        self.assertEqual(a["annotation"], b["annotation"])
        self.assertEqual(b["translation"]["status"], "needs_review")
        self.assertNotEqual(a["translation"]["task_key"], b["translation"]["task_key"])

    def test_annotation_prompt_revision_does_not_invalidate_translation(self):
        self.seed(); self.translation()
        e = self.entry(policies=task_policies(annotation_revision="annotation-next"))
        self.assertEqual(e["translation"]["status"], "reuse_existing")
        self.assertEqual(e["annotation"]["status"], "needs_review")

    def test_missing_legacy_policy_requires_review(self):
        self.seed(processing_policy=None)
        self.assertEqual(self.entry()["annotation"]["status"], "needs_review")

    def test_unavailable_editorial_status_is_semantically_equivalent(self):
        self.seed(raw(editorial_status="not_found"))
        self.assertEqual(self.entry(raw(editorial_status="missing"))["annotation"]["status"], "reuse_existing")

    def test_original_request_hash_is_required_even_with_same_labels(self):
        self.seed(annotation_input_hash="0" * 64)
        self.assertEqual(self.entry()["annotation"]["reason"], "legacy_annotation_input_binding_unverified")

    def test_available_editorial_change_is_not_ignored(self):
        p = raw(editorial_status="ok", verified_editorial_markdown="A verified synthetic proof.")
        self.seed(p)
        e = self.entry(raw(editorial_status="ok", verified_editorial_markdown="A different verified proof."))
        self.assertEqual(e["annotation"]["status"], "needs_review")

    def test_legacy_cache_equivalent_input_can_be_reused(self):
        self.cached()
        e = self.entry()
        self.assertEqual(e["annotation"]["status"], "reuse_existing")
        self.assertEqual(e["annotation"]["existing_result"]["kind"], "annotation_cache")

    def test_unproven_legacy_cache_blocks_new_payment(self):
        self.cached(processing_policy=None)
        e = self.entry()
        self.assertEqual(e["annotation"]["status"], "needs_review")
        self.assertFalse(e["annotation"]["needs_ai"])

    def test_conflicting_successful_caches_require_review(self):
        self.cached()
        self.cached(specific_tag_ids=["prefix_sum"])
        self.assertEqual(self.entry()["annotation"]["status"], "needs_review")

    def test_unknown_delivery_with_identity_blocks_only_affected_task(self):
        save(self.cache / "unknown.json", {"state": "unknown_delivery", "problem_key": raw()["problem_key"]})
        e = self.entry()
        self.assertEqual(e["annotation"]["status"], "needs_review")
        self.assertEqual(e["translation"]["status"], "needs_translation")
        self.assertEqual(self.entry(raw(1))["annotation"]["status"], "needs_annotation")

    def test_unassigned_delivery_blocks_all_annotation_tasks(self):
        save(self.cache / "unknown.json", {"state": "unknown_delivery"})
        self.assertEqual(self.entry()["annotation"]["status"], "needs_review")
        self.assertEqual(self.entry(raw(1))["annotation"]["status"], "needs_review")

    def test_sent_and_received_requests_are_not_automatically_reissued(self):
        for state in ("sent", "received", "retry_wait", "failed"):
            with self.subTest(state=state):
                save(self.cache / "request.json", {"state": state, "problem_key": raw()["problem_key"]})
                self.assertFalse(self.entry()["annotation"]["needs_ai"])

    def test_corrupt_cache_fails_closed(self):
        self.cache.mkdir()
        (self.cache / "corrupt.json").write_text("{", encoding="utf-8")
        self.assertEqual(self.entry()["annotation"]["status"], "needs_review")

    def test_unassigned_translation_request_does_not_invalidate_annotation(self):
        self.seed()
        save(self.repo.root / "translations/requests/unknown.json", {"state": "unknown_delivery"})
        e = self.entry()
        self.assertEqual(e["annotation"]["status"], "reuse_existing")
        self.assertEqual(e["translation"]["status"], "needs_review")

    def test_html_without_reliable_conversion_is_pending(self):
        e = self.entry(raw(statement_markdown="", statement_html="<div>Unverified body</div>"))
        self.assertEqual(e["status"], "pending")
        self.assertFalse(e["needs_ai"])

    def test_pdf_only_is_pending(self):
        e = self.entry({"platform": "atcoder", "problem_id": "offline_0", "contest_id": "offline",
                        "problem_name": "Mock PDF", "statement_pdf": "problem.pdf", "last_fetch_status": "ok"})
        self.assertEqual(e["status"], "pending")
        self.assertFalse(e["needs_ai"])

    def test_missing_body_is_pending(self):
        self.assertEqual(self.entry(raw(statement_markdown=""))["status"], "pending")

    def test_invalid_identity_is_isolated(self):
        p = self.planner().plan([{"platform": "atcoder"}, raw()])
        self.assertEqual(p["summary"]["invalid"], 1)
        self.assertEqual(p["summary"]["total"], 2)

    def test_duplicate_input_is_deduplicated(self):
        p = self.planner().plan([raw(), raw()])
        self.assertEqual(p["summary"]["estimated_api_tasks"], 2)
        self.assertEqual(p["summary"]["duplicates"], 1)

    def test_conflicting_duplicate_identity_is_invalid(self):
        p = self.planner().plan([raw(), raw(title="Different title")])
        self.assertEqual(p["summary"]["invalid"], 1)
        self.assertEqual(p["summary"]["estimated_api_tasks"], 0)

    def test_repeated_planning_is_identical_and_source_immutable(self):
        self.seed()
        source = raw()
        before = deepcopy(source)
        files = {p.relative_to(self.repo.root): p.read_bytes() for p in self.repo.root.rglob("*") if p.is_file()}
        a, b = self.planner().plan([source]), self.planner().plan([source])
        self.assertEqual(a, b)
        self.assertEqual(source, before)
        self.assertEqual(files, {p.relative_to(self.repo.root): p.read_bytes() for p in self.repo.root.rglob("*") if p.is_file()})

    def test_plan_order_is_stable(self):
        self.assertEqual(self.planner().plan([raw(1), raw(0)]), self.planner().plan([raw(0), raw(1)]))

    def test_plan_never_exports_statement_or_editorial(self):
        p = self.planner().plan([raw(statement_markdown="PRIVATE_SOURCE_MARKER with enough English words.")])
        self.assertNotIn("PRIVATE_SOURCE_MARKER", json.dumps(p))

    def test_successful_empty_labels_are_reused(self):
        self.seed(specific_tag_ids=[])
        e = self.entry()
        self.assertEqual(e["effective_tags"], [])
        self.assertEqual(e["annotation"]["status"], "reuse_existing")

    def test_mock_translation_is_not_real_result(self):
        self.seed(); self.translation(translation_status="mock", translation_model="mock-translation")
        self.assertEqual(self.entry()["translation"]["status"], "needs_review")

    def test_legacy_translation_without_prompt_proof_requires_review(self):
        self.seed(); self.translation(processing_policy=None)
        self.assertEqual(self.entry()["translation"]["status"], "needs_review")

    def test_old_bilingual_text_change_affects_labels_but_not_selected_translation(self):
        en = "\nProblem Statement\nYou are given two integers. Print their sum.\nConstraints\nInput\nOutput\n"
        p = raw(statement_markdown="あいうえお\n" + en)
        self.seed(p); self.translation(p)
        e = self.entry(raw(statement_markdown="かきくけこ\n" + en))
        self.assertEqual(e["annotation"]["status"], "needs_review")
        self.assertEqual(e["translation"]["status"], "reuse_existing")

    def test_atomic_plan_write_and_no_overwrite(self):
        output = self.base / "plans"
        p = self.planner().plan([raw()])
        with patch("problem_processing.planning.OUTPUT_ROOT", output):
            target = output / "test.json"
            write_plan(target, p)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), p)
            with self.assertRaises(ValueError):
                write_plan(target, {})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), p)

    def test_unsafe_output_paths_rejected(self):
        with patch("problem_processing.planning.OUTPUT_ROOT", self.base / "plans"):
            for target in (self.base / "outside.json", self.base / "plans" / "../outside.json", self.base / "plans/file.txt"):
                with self.subTest(path=target), self.assertRaises(ValueError):
                    write_plan(target, {})

    def test_failed_atomic_publication_leaves_no_target_or_temp(self):
        output = self.base / "plans"
        with patch("problem_processing.planning.OUTPUT_ROOT", output), patch(
                "problem_processing.planning.os.link", side_effect=OSError("Mock publication failure")):
            with self.assertRaises(OSError):
                write_plan(output / "test.json", {"ok": True})
        self.assertEqual(list(output.iterdir()), [])

    def test_cli_defaults_to_dry_run_and_has_no_execute_flag(self):
        source = self.base / "input.json"
        save(source, [raw()])
        out = io.StringIO()
        with redirect_stdout(out):
            code = plan_processing.main(["--input", str(source), "--data-root", str(self.repo.root),
                                         "--cache-root", str(self.cache), "--manifest-root", str(self.base / "none")])
        result = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertFalse(result["output_written"])
        self.assertEqual(result["summary"]["real_api_calls"], 0)
        self.assertFalse(result["execution_supported"])

    def test_planning_never_loads_dotenv(self):
        with patch("dotenv.load_dotenv", side_effect=AssertionError("Credentials must not be loaded")):
            self.assertEqual(self.planner().plan([raw()])["summary"]["real_api_calls"], 0)

    def test_legacy_manifest_proves_policy_without_adapter_path_dependency(self):
        import hashlib
        from label_pipeline import BASE
        policy = task_policies()["annotation"]
        profile = {"prompt_version": policy["revision"], "prompt_hash": policy["prompt_hash"],
                   "schema_hash": policy["schema_hash"], "taxonomy_version": TAXONOMY["version"],
                   "rule_version": policy["rule_version"], "implementation_hashes": {
                       name: hashlib.sha256((BASE / name).read_bytes()).hexdigest()
                       for name in ("tag_taxonomy_v0.3.json", "cf_mapping_v0.3.json")}}
        profile["implementation_hashes"]["adapter.py"] = "changed implementation, same input"
        profile["config"] = {"model": "offline-model", "base_url": "https://example.invalid/v1"}
        profile_id = digest(profile)
        self.seed(processing_policy=None, profile_id=profile_id)
        manifests = self.base / "manifests"
        save(manifests / "manifest.json", {"profile_id": profile_id, "profile": profile})
        planner = Planner(self.repo.root, cache_roots=[self.cache], manifest_roots=[manifests])
        self.assertEqual(planner.plan([raw()])["entries"][0]["annotation"]["status"], "reuse_existing")

    def test_legacy_missing_editorial_field_needs_original_hash_proof(self):
        self.seed(raw(editorial_status="ambiguous"))
        planner = self.planner()
        old = planner.problems[raw()["problem_key"]]
        for field in ("input_adapter_version", "verified_editorial_markdown", "editorial_status", "editorial_evidence_kind"):
            old.pop(field, None)
        e = planner.plan([raw()])["entries"][0]
        self.assertEqual(e["annotation"]["status"], "reuse_existing")

    def test_persisted_and_cache_conflict_requires_review(self):
        self.seed()
        self.cached(specific_tag_ids=["prefix_sum"])
        e = self.entry()
        self.assertEqual(e["annotation"]["reason"], "persistent_and_cached_labels_conflict")

    def test_manual_reset_returns_current_automatic_tags(self):
        self.seed()
        self.repo.manager().change(raw()["problem_key"], "remove", ["enumeration"])
        self.repo.manager().change(raw()["problem_key"], "reset")
        self.assertEqual([t["id"] for t in self.entry()["effective_tags"]], ["enumeration"])

    def test_changed_input_does_not_present_old_effective_tags_as_current(self):
        self.seed()
        e = self.entry(raw(statement_markdown="A different problem with changed constraints."))
        self.assertFalse(e["effective_tags_are_current_input"])
        self.assertEqual([t["id"] for t in e["effective_tags"]], ["enumeration"])

    def test_jsonl_cli_input_and_safe_write(self):
        source = self.base / "input.jsonl"
        source.write_text(json.dumps(raw()) + "\n", encoding="utf-8")
        output = self.base / "plans/test.json"
        with patch("problem_processing.planning.OUTPUT_ROOT", output.parent), redirect_stdout(io.StringIO()):
            result = plan_processing.main(["--input", str(source), "--data-root", str(self.repo.root), "--cache-root", str(self.cache),
                                           "--manifest-root", str(self.base / "none"), "--write", "--output", str(output)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["estimated_api_tasks"], 2)

    def test_sensitive_plan_payload_is_not_published(self):
        with patch("problem_processing.planning.OUTPUT_ROOT", self.base / "plans"):
            with self.assertRaises(ValueError):
                write_plan(self.base / "plans/test.json", {"authorization": "synthetic-secret"})
        self.assertFalse((self.base / "plans/test.json").exists())

    def test_existing_demo_reads_actual_plan_summary(self):
        from demo_acceptance import load_processing_plan
        self.seed()
        summary = load_processing_plan(self.repo.root)["summary"]
        self.assertEqual(summary["annotation_reused"], 1)
        self.assertEqual(summary["needs_translation"], 1)
        self.assertEqual(summary["real_api_calls"], 0)

    def test_demo_plan_area_displays_real_counts_and_execution_boundary(self):
        import demo_acceptance as demo
        self.seed()
        data = {"live": demo.load_live(self.repo.root), "tests": None,
                "git": {"branch": "offline", "commit": "test-only", "dirty": True}, "generated_at": "offline-test",
                "manual": demo.manual_demo(), "translations": demo.translation_demo(),
                "backups": {"reports": []}, "planning": demo.load_processing_plan(self.repo.root)}
        page = demo.render_page(data)
        self.assertIn('id="planning"', page)
        self.assertIn("复用已有结果", page)
        self.assertIn("缺少中文翻译", page)
        self.assertIn("7G 已接入发送前重检", page)
        self.assertIn("尚不保证上游恰好计费一次", page)
        self.assertNotIn("@@PROCESSING_PLAN@@", page)


class SavedAtCoderPlanningTests(unittest.TestCase):
    def test_existing_saved_ten_labels_are_reused_read_only(self):
        # Optional local acceptance evidence; portable tests above need no private statements.
        repo = Repository()
        if not repo.pointer.exists():
            self.skipTest("本机没有私有持久数据；合成数据测试不依赖此文件")
        problems, labels = repo.snapshot()
        if len(problems) != 10 or any(p["platform"] != "atcoder" for p in problems.values()):
            self.skipTest("不是本阶段指定的 10 题本地探索快照")
        before = {p.relative_to(repo.root): p.read_bytes() for p in repo.root.rglob("*") if p.is_file()}
        plan = Planner().plan(list(problems.values()))
        self.assertEqual(plan["summary"]["annotation_reused"], 10)
        self.assertEqual(plan["summary"]["needs_annotation"], 0)
        self.assertEqual(plan["summary"]["invalid"], 0)
        self.assertEqual(before, {p.relative_to(repo.root): p.read_bytes() for p in repo.root.rglob("*") if p.is_file()})


if __name__ == "__main__":
    unittest.main()
