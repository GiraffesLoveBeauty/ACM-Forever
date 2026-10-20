"""Synthetic JSONL and local mocks only; never open an SDK or call an API."""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import manage_tags
from label_pipeline import TAG_BY_ID, TAXONOMY
from tag_management import TagManager, get_effective_tags
from tag_management.model import resolve_tag
from tag_management.service import automatic_path
from tag_management.storage import Journal

KEY = "atcoder:offline:offline_a"
OTHER = "atcoder:offline:offline_b"
CF = "codeforces:999999:A"


def record(key=KEY, **overrides):
    return {"problem_key": key, "platform": key.split(":")[0], "title": "仅供离线测试的题目",
            "specific_tag_ids": ["enumeration"], "provisional_tag_ids": [],
            "taxonomy_version": TAXONOMY["version"], "content_hash": "offline-content-v1",
            "raw_tags": [], "model": "offline-model", "api_call_status": "success",
            "human_review_status": "pending_review", "review_status": "ai_suggested_pending_human_review",
            **overrides}


class ManualTagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.auto = self.root / "auto.jsonl"
        self.overrides = self.root / "manual_labels" / "overrides.jsonl"
        self.rows = [record(), record(OTHER)]
        self.save()
        self.manager = TagManager(self.auto, self.overrides)

    def tearDown(self):
        self.temp.cleanup()

    def save(self):
        self.auto.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in self.rows), encoding="utf-8")

    def view(self, key=KEY):
        return self.manager.get_effective_tags(key)

    def edit(self, command, tags=(), key=KEY):
        return self.manager.change(key, command, tags, actor="测试管理员", reason="离线纠错测试")

    def test_automatic_pending_results_effective_without_human_verification(self):
        result = self.view()
        self.assertEqual(result["specific_tag_ids"], ["enumeration"])
        self.assertEqual(result["review_status"], "auto")
        self.assertTrue(result["recommendation_eligible"])
        self.assertFalse(result["fully_human_verified"])
        self.assertEqual(result["effective_tags"][0]["source"], "ai")
        self.assertFalse(self.overrides.parent.exists())

    def test_public_query_function_and_chinese_name(self):
        result = get_effective_tags(KEY, auto_file=self.auto, override_file=self.overrides)
        self.assertEqual(result["specific_tag_names_zh"], ["枚举"])

    def test_add_chinese_and_id_preserves_provenance(self):
        result = self.edit("add", ["前缀和", "prefix_sum"])
        self.assertTrue(result["changed"])
        self.assertEqual(self.view()["manual_overrides"]["added_tag_ids"], ["prefix_sum"])
        self.assertEqual(self.view()["review_status"], "corrected")
        self.assertEqual(next(t for t in self.view()["effective_tags"] if t["id"] == "prefix_sum")["source"], "manual_add")
        self.assertFalse(self.view()["fully_human_verified"])

    def test_remove_to_empty_and_original_prediction_untouched(self):
        before = self.auto.read_bytes()
        self.edit("remove", ["枚举"])
        self.assertEqual(self.view()["specific_tag_ids"], [])
        self.assertEqual(self.view()["auto_tags"]["tag_ids"], ["enumeration"])
        self.assertEqual(self.auto.read_bytes(), before)

    def test_replace(self):
        self.edit("replace", ["enumeration", "simulation"])
        state = self.view()["manual_overrides"]
        self.assertEqual(state["added_tag_ids"], ["simulation"])
        self.assertEqual(state["removed_tag_ids"], ["enumeration"])
        self.assertEqual(self.view()["specific_tag_ids"], ["simulation"])

    def test_repeated_operations_do_not_duplicate_history(self):
        for command, tags in [("add", ["prefix_sum"]), ("remove", ["enumeration"]),
                              ("replace", ["prefix_sum", "simulation"])]:
            self.edit(command, tags)
            before = self.overrides.read_bytes()
            self.assertFalse(self.edit(command, tags)["changed"])
            self.assertEqual(self.overrides.read_bytes(), before)

    def test_opposite_operation_clears_intersection(self):
        self.edit("remove", ["enumeration"])
        self.edit("add", ["enumeration"])
        state = self.view()["manual_overrides"]
        self.assertEqual(state["removed_tag_ids"], [])
        self.assertEqual(state["added_tag_ids"], ["enumeration"])
        self.edit("remove", ["enumeration"])
        self.assertEqual(self.view()["manual_overrides"]["added_tag_ids"], [])

    def test_ai_rerun_cannot_restore_deleted_or_remove_added_tags(self):
        self.edit("remove", ["enumeration"])
        self.edit("add", ["prefix_sum"])
        self.rows[0]["specific_tag_ids"] = ["enumeration", "simulation"]
        self.save()
        self.assertEqual(set(self.view()["specific_tag_ids"]), {"prefix_sum", "simulation"})
        self.assertEqual(self.view()["review_status"], "corrected")

    def test_removed_absent_tag_blocks_future_prediction(self):
        self.edit("remove", ["sieve"])
        self.rows[0]["specific_tag_ids"] = ["enumeration", "sieve"]
        self.save()
        self.assertNotIn("sieve", self.view()["specific_tag_ids"])

    def test_adding_existing_auto_tag_pins_it(self):
        self.edit("add", ["enumeration"])
        self.assertEqual(self.view()["effective_tags"][0]["sources"], ["ai", "manual_add"])
        self.rows[0]["specific_tag_ids"] = []
        self.save()
        self.assertEqual(self.view()["specific_tag_ids"], ["enumeration"])

    def test_reset_restores_current_not_original_auto_labels(self):
        self.edit("remove", ["enumeration"])
        self.rows[0]["specific_tag_ids"] = ["enumeration", "simulation"]
        self.save()
        self.edit("reset")
        self.assertEqual(set(self.view()["specific_tag_ids"]), {"enumeration", "simulation"})
        self.assertEqual(self.view()["review_status"], "auto")
        self.assertEqual(len(self.manager.history(KEY)), 2)
        self.assertFalse(self.edit("reset")["changed"])

    def test_undo_keeps_auditable_history(self):
        self.edit("remove", ["enumeration"])
        self.edit("add", ["simulation"])
        self.edit("undo")
        self.assertEqual(self.view()["specific_tag_ids"], [])
        history = self.manager.history(KEY)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[-1]["details"]["undo_event_id"], history[-2]["event_id"])

    def test_undo_reset_restores_tombstones(self):
        self.edit("remove", ["enumeration"])
        self.edit("reset")
        self.edit("undo")
        self.assertEqual(self.view()["specific_tag_ids"], [])

    def test_undo_without_history_is_noop(self):
        self.assertFalse(self.edit("undo")["changed"])
        self.assertFalse(self.overrides.exists())

    def test_valid_empty_and_provisional_tags(self):
        self.rows[0]["specific_tag_ids"] = []
        self.save()
        self.assertEqual(self.view()["review_status"], "auto")
        self.edit("add", ["pending_dp"])
        self.assertEqual(self.view()["provisional_tag_ids"], ["pending_dp"])
        self.assertEqual(self.view()["specific_tag_ids"], [])

    def test_invalid_tag_and_replace_rejected_without_history(self):
        for operation, tags in [("add", ["invented_algorithm"]), ("replace", ["enumeration", "枚举"]),
                                ("replace", ["sieve", "simulation"])]:
            with self.assertRaises(ValueError):
                self.edit(operation, tags)
        self.assertFalse(self.overrides.exists())

    def test_history_survives_restarting_and_records_actor_reason(self):
        self.edit("add", ["前缀和"])
        manager = TagManager(self.auto, self.overrides)
        event = manager.history(KEY)[0]
        self.assertEqual(event["actor"], "测试管理员")
        self.assertEqual(event["reason"], "离线纠错测试")
        self.assertTrue(event["created_at"].endswith("+00:00"))
        self.assertEqual(manager.get_effective_tags(KEY)["manual_overrides"]["added_tag_ids"], ["prefix_sum"])

    def test_multiple_problem_operations_are_isolated(self):
        self.edit("remove", ["enumeration"])
        self.assertEqual(self.view(OTHER)["specific_tag_ids"], ["enumeration"])
        self.edit("add", ["prefix_sum"], key=OTHER)
        self.assertEqual(self.view()["specific_tag_ids"], [])
        self.assertEqual(len(self.manager.history(KEY)), 1)
        self.assertEqual(len(self.manager.list_overrides()), 2)

    def test_content_change_retains_edits_and_marks_review(self):
        self.edit("remove", ["enumeration"])
        self.rows[0]["content_hash"] = "offline-content-v2"
        self.save()
        self.assertEqual(self.view()["specific_tag_ids"], [])
        self.assertEqual(self.view()["review_status"], "needs_review")
        self.assertIn("content_changed_since_manual_edit", self.view()["needs_review_reasons"])
        self.assertFalse(self.view()["recommendation_eligible"])
        self.edit("add", ["simulation"])
        self.assertEqual(self.view()["review_status"], "needs_review")
        self.assertEqual(self.view()["manual_overrides"]["anchor_content_hash"], "offline-content-v1")

    def test_verification_is_explicit_and_stales_on_new_labels(self):
        self.edit("verify")
        self.assertEqual(self.view()["review_status"], "verified")
        self.assertTrue(self.view()["fully_human_verified"])
        self.rows[0]["specific_tag_ids"].append("sieve")
        self.save()
        self.assertEqual(self.view()["review_status"], "needs_review")
        self.assertIn("automatic_labels_changed_since_verification", self.view()["needs_review_reasons"])
        self.edit("verify")
        self.assertEqual(self.view()["review_status"], "verified")

    def test_verification_can_acknowledge_new_content_without_losing_edits(self):
        self.edit("remove", ["enumeration"])
        self.rows[0]["content_hash"] = "offline-content-v2"
        self.save()
        self.edit("verify")
        self.assertEqual(self.view()["review_status"], "verified")
        self.assertEqual(self.view()["specific_tag_ids"], [])

    def test_correction_clears_previous_verification(self):
        self.edit("verify")
        self.edit("add", ["prefix_sum"])
        self.assertEqual(self.view()["review_status"], "corrected")
        self.assertFalse(self.view()["fully_human_verified"])

    def test_legacy_human_confirmed_is_verified(self):
        self.rows[0].update(review_status="human_confirmed", human_review_status="approved")
        self.save()
        self.assertEqual(self.view()["review_status"], "verified")
        self.assertEqual(self.view()["effective_tags"][0]["source"], "legacy_human")

    def test_missing_hash_with_manual_edits_needs_review(self):
        self.rows[0]["content_hash"] = None
        self.save()
        self.edit("add", ["simulation"])
        self.assertEqual(self.view()["review_status"], "needs_review")
        with self.assertRaises(ValueError):
            self.edit("verify")

    def test_failed_or_uncertain_automatic_record_not_recommended(self):
        for status in ["failed", "unknown_delivery"]:
            self.rows[0]["api_call_status"] = status
            self.save()
            self.assertEqual(self.view()["review_status"], "needs_review")
            self.assertFalse(self.view()["recommendation_eligible"])
            with self.assertRaises(ValueError):
                self.edit("verify")

    def test_cf_precise_mapping_restored_and_admin_can_correct(self):
        self.rows = [record(CF, raw_tags=["dsu"], specific_tag_ids=[], api_call_status="not_required")]
        self.save()
        result = self.view(CF)
        self.assertEqual(result["specific_tag_ids"], ["dsu"])
        self.assertEqual(result["effective_tags"][0]["source"], "cf_rule_mapping")
        self.edit("remove", ["并查集"], key=CF)
        self.assertEqual(self.view(CF)["specific_tag_ids"], [])
        self.assertEqual(self.manager.history(CF)[0]["automatic_snapshot"]["origins"]["dsu"], "cf_rule_mapping")
        self.rows[0]["specific_tag_ids"] = ["dsu"]
        self.save()
        self.assertEqual(self.view(CF)["specific_tag_ids"], [])

    def test_cf_ai_predictions_use_existing_merged_evaluation_tags(self):
        self.rows = [record(CF, raw_tags=["dsu", "data structures"], specific_tag_ids=["segment_tree"],
                            evaluation_specific_tag_ids=["dsu", "segment_tree"],
                            evaluation_provisional_tag_ids=["pending_data_structures"])]
        self.save()
        result = self.view(CF)
        self.assertEqual(set(result["specific_tag_ids"]), {"dsu", "segment_tree"})
        self.assertEqual(result["provisional_tag_ids"], ["pending_data_structures"])

    def test_invalid_automatic_ids_versions_and_duplicate_identities_fail_closed(self):
        for bad in [record(specific_tag_ids=["invented"]), record(taxonomy_version="old"),
                    record(specific_tag_ids=["pending_dp"]), record(platform="codeforces")]:
            self.rows = [bad]; self.save()
            with self.assertRaises(ValueError):
                self.view()
        self.rows = [record(), record()]; self.save()
        with self.assertRaises(ValueError):
            self.view()

    def test_invalid_identity_and_unknown_problem(self):
        for key in ["atcoder:offline", "atcoder:offline:missing", "unknown:offline:a"]:
            with self.assertRaises(ValueError):
                self.manager.get_effective_tags(key)

    def test_list_retains_orphans_after_automatic_dataset_changes(self):
        self.edit("add", ["simulation"])
        self.rows = [record(OTHER)]; self.save()
        listed = self.manager.list_overrides()
        self.assertEqual(listed[0]["problem_key"], KEY)
        self.assertEqual(listed[0]["review_status"], "needs_review")
        self.assertEqual(len(self.manager.history(KEY)), 1)

    def test_journal_cannot_be_placed_in_disposable_locations(self):
        for folder in ["outputs", "cache"]:
            with self.assertRaises(ValueError):
                TagManager(self.auto, self.root / folder / "overrides.jsonl")
        with self.assertRaises(ValueError):
            TagManager(self.auto, self.auto)

    def test_atomic_replace_failure_preserves_old_history_and_cleans_temp(self):
        self.edit("add", ["prefix_sum"])
        before = self.overrides.read_bytes()
        with patch("tag_management.storage.os.replace", side_effect=OSError("offline simulated disk failure")):
            with self.assertRaises(OSError):
                self.edit("remove", ["enumeration"])
        self.assertEqual(self.overrides.read_bytes(), before)
        self.assertEqual(list(self.overrides.parent.glob(".override-*.tmp")), [])
        self.assertIn("enumeration", self.view()["specific_tag_ids"])

    def test_writer_lock_blocks_concurrent_edit_without_lost_update(self):
        self.edit("add", ["prefix_sum"])
        with self.manager.journal.locked():
            with self.assertRaises(ValueError):
                self.edit("remove", ["enumeration"])
        self.assertEqual(len(self.manager.history(KEY)), 1)

    def test_corrupt_or_truncated_history_never_silently_repaired(self):
        self.edit("add", ["prefix_sum"])
        with self.overrides.open("a", encoding="utf-8") as stream:
            stream.write('{"partial":')
        before = self.overrides.read_bytes()
        with self.assertRaises(ValueError):
            self.edit("remove", ["enumeration"])
        self.assertEqual(self.overrides.read_bytes(), before)

    def test_intersecting_sets_or_broken_event_chain_rejected(self):
        self.edit("add", ["prefix_sum"])
        event = self.manager.history(KEY)[0]
        bad = deepcopy(event); bad["after"]["removed_tag_ids"] = ["prefix_sum"]
        self.overrides.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.view()
        bad = deepcopy(event); bad["previous_event_id"] = "missing-event"
        self.overrides.write_text(json.dumps(bad) + "\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.view()

    def test_pinned_default_source_config_does_not_guess_latest_model(self):
        settings = self.root / "settings.json"
        settings.write_text(json.dumps({"schema_version": 1, "auto_file": str(self.auto)}), encoding="utf-8")
        with patch("tag_management.service.DEFAULT_SETTINGS", settings):
            self.assertEqual(automatic_path(), self.auto.resolve())
            self.assertEqual(TagManager(override_file=self.overrides).get_effective_tags(KEY)["review_status"], "auto")

    def test_chinese_cli_crud_history_and_errors(self):
        options = ["--auto-file", str(self.auto), "--overrides", str(self.overrides), "--actor", "离线管理员", "--reason", "测试"]
        commands = [["show", KEY], ["add", KEY, "前缀和"], ["remove", KEY, "枚举"],
                    ["replace", KEY, "prefix_sum", "simulation"], ["history", KEY], ["list"],
                    ["undo", KEY], ["reset", KEY], ["verify", KEY]]
        for command in commands:
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(manage_tags.main(options + command), 0)
            data = json.loads(output.getvalue())
            self.assertIn("message", data)
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(manage_tags.main(options + ["add", KEY, "nonexistent"]), 2)
        self.assertIn("操作失败", error.getvalue())


if __name__ == "__main__":
    unittest.main()
