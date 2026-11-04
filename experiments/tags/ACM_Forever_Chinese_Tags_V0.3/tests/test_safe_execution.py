"""Mock-only executor safety, actual child processes, no live credentials or network."""
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import httpx
import annotate_api
import execute_processing
import translate_api
from annotation_api.adapter import digest
from annotation_api.client import APIClient, CallError, Response
from annotation_api.dispatch import request_settings
from annotation_api.runner import run
from problem_processing.adapter import normalize
from problem_processing.backup import create_backup, restore_backup
from problem_processing.execution_state import Ledger
from problem_processing.executor import Executor, MockAnnotationClient, bind_plan, execute_batch, mock_config, task_identity
from problem_processing.planning import Planner
from problem_processing.repository import Repository
from problem_processing.translation import MockTranslationClient, translate


def raw(number=0, **values):
    return {"platform": "atcoder", "problem_key": f"atcoder:offline:offline_{number}", "title": "Mock Addition",
            "statement_markdown": "You are given two integers. Print their sum.", "statement_status": "ok", **values}


class MemoryTransport(httpx.BaseTransport):
    """Behaves like the production transport for gate checks, but never opens a socket."""
    def __init__(self, callback=None):
        self.calls = 0
        self.callback = callback

    def handle_request(self, request):
        self.calls += 1
        if self.callback:
            return self.callback(request)
        data = json.loads(request.content)
        response = MockAnnotationClient().call(data["messages"])
        return httpx.Response(200, json={"id": "mock", "object": "chat.completion", "created": 0,
            "model": "memory-transport-mock", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": response.content}}], "usage": {"prompt_tokens": 9, "completion_tokens": 4, "total_tokens": 13}})


class SafeExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-execution-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "labels"
        self.cfg = mock_config()
        guard = patch("httpx.HTTPTransport.handle_request", side_effect=AssertionError("Real HTTP forbidden"))
        guard.start(); self.addCleanup(guard.stop)

    def batch(self, rows=None, task="annotation", **kwargs):
        return execute_batch(rows or [raw()], task, root=self.root, mock=True, config=self.cfg,
                             cache_roots=[], manifest_roots=[], **kwargs)

    def plan(self, rows=None):
        return Planner(self.root, cache_roots=[], manifest_roots=[]).plan(rows or [raw()])

    def client(self, transport=None, hooks=None):
        transport = transport or MemoryTransport()
        http = httpx.Client(transport=transport, trust_env=False, event_hooks={"request": hooks or []})
        client = APIClient(self.cfg, http_client=http)
        self.addCleanup(client.close)
        return client, transport

    def live_simulation(self, client, **kwargs):
        plan = bind_plan(self.plan(), "annotation", request_settings(self.cfg))
        return execute_batch([raw()], "annotation", root=self.root, execute=True, config=self.cfg,
                             client=client, plan=plan, cache_roots=[], manifest_roots=[], **kwargs)

    def test_mock_annotation_full_flow_persists_result_and_usage(self):
        r = self.batch()
        self.assertEqual((r["completed"], r["api_calls"], r["real_api_calls"]), (1, 1, 0))
        rows = Ledger(self.root).records()
        self.assertEqual(rows[0]["state"], "completed")
        self.assertTrue(rows[0]["result_sha256"])
        self.assertEqual(len(Repository(self.root).snapshot()[0]), 1)

    def test_repeated_task_does_not_call_client_again(self):
        c = MockAnnotationClient()
        self.batch(client=c)
        second = self.batch(client=c)
        self.assertEqual(c.calls, 1)
        self.assertEqual((second["reused"], second["api_calls"]), (1, 0))

    def test_translation_mock_full_flow_and_reuse(self):
        client = MockTranslationClient()
        first = self.batch(task="translation", client=client)
        second = self.batch(task="translation", client=client)
        self.assertEqual((first["completed"], second["reused"], client.calls), (1, 1, 1))
        self.assertEqual(first["results"][0]["result"]["translation_status"], "mock")

    def test_tasks_have_independent_identity(self):
        p = normalize(raw())
        self.assertNotEqual(task_identity(p, "annotation", self.cfg), task_identity(p, "translation", self.cfg))

    def test_irrelevant_paths_and_timeout_do_not_change_task_identity(self):
        p = normalize(raw())
        other = normalize(raw(output_path="X:/other", fetched_at="2030-01-01"))
        self.assertEqual(task_identity(p, "annotation", self.cfg), task_identity(other, "annotation", mock_config(timeout=3)))

    def test_model_and_output_parameters_change_task_id(self):
        p = normalize(raw())
        for cfg in (mock_config(model="different"), mock_config(max_output_tokens=55), mock_config(response_format="json_object"),
                    mock_config(token_parameter="max_tokens")):
            with self.subTest(cfg=cfg):
                self.assertNotEqual(digest(task_identity(p, "annotation", self.cfg)), digest(task_identity(p, "annotation", cfg)))

    def test_translation_prompt_change_does_not_change_annotation_identity(self):
        p = normalize(raw())
        before = task_identity(p, "annotation", self.cfg), task_identity(p, "translation", self.cfg)
        with patch("problem_processing.translation.SYSTEM", "changed translation prompt"):
            self.assertEqual(before[0], task_identity(p, "annotation", self.cfg))
            self.assertNotEqual(before[1], task_identity(p, "translation", self.cfg))

    def test_annotation_schema_change_does_not_change_translation_identity(self):
        p = normalize(raw())
        before = task_identity(p, "annotation", self.cfg), task_identity(p, "translation", self.cfg)
        with patch("annotation_api.schema.SCHEMA", {"changed": True}):
            self.assertNotEqual(before[0], task_identity(p, "annotation", self.cfg))
            self.assertEqual(before[1], task_identity(p, "translation", self.cfg))

    def test_persisted_annotation_is_reused_without_execution_record(self):
        from test_processing_plan import annotation
        Repository(self.root).import_records([raw()], [annotation(raw())])
        c = MockAnnotationClient()
        r = self.batch(client=c)
        self.assertEqual((c.calls, r["reused"]), (0, 1))
        self.assertEqual(Ledger(self.root).records(), [])

    def test_manual_tombstones_are_preserved_on_reuse(self):
        self.batch()
        manager = Repository(self.root).manager()
        manager.change(raw()["problem_key"], "remove", ["enumeration"])
        manager.change(raw()["problem_key"], "add", ["prefix_sum"])
        before = manager.journal.path.read_bytes()
        r = self.batch()
        self.assertEqual(r["api_calls"], 0)
        self.assertEqual(before, manager.journal.path.read_bytes())
        self.assertEqual([t["id"] for t in r["results"][0]["effective_tags"]], ["prefix_sum"])

    def test_manual_correction_of_incomplete_auto_baseline_blocks_annotation(self):
        repo = Repository(self.root)
        repo.import_records([raw()])
        repo.manager().change(raw()["problem_key"], "add", ["prefix_sum"])
        r = self.batch()
        self.assertEqual((r["blocked"], r["api_calls"]), (1, 0))

    def test_local_failure_before_dispatch_can_retry(self):
        def fail(stage, row):
            if stage == "claimed":
                raise ValueError("Mock preparation error")
        first = self.batch(checkpoint=fail)
        self.assertEqual(first["api_calls"], 0)
        self.assertEqual(Ledger(self.root).records()[0]["state"], "failed_before_dispatch")
        self.assertEqual(self.batch()["completed"], 1)
        self.assertEqual(len(Ledger(self.root).records()[0]["attempts"]), 2)

    def test_timeout_is_uncertain_and_never_resent(self):
        class Timeout(MockAnnotationClient):
            def call(self, *args, **kwargs):
                self.calls += 1
                raise CallError("unknown_delivery", unknown=True)
        c = Timeout()
        first, second = self.batch(client=c), self.batch(client=c)
        self.assertEqual(c.calls, 1)
        self.assertEqual(first["results"][0]["status"], "uncertain")
        self.assertEqual(second["api_calls"], 0)

    def test_old_timestamp_does_not_expire_uncertain(self):
        def crash(stage, row):
            if stage == "dispatched":
                raise SystemExit("Mock exit")
        with self.assertRaises(SystemExit):
            self.batch(checkpoint=crash)
        ledger = Ledger(self.root)
        row = ledger.records()[0]
        row["created_at"] = row["updated_at"] = "2000-01-01T00:00:00+00:00"
        ledger.save(row)
        self.assertEqual(self.batch()["api_calls"], 0)

    def test_saved_response_recovered_without_call(self):
        def stop(stage, row):
            if stage == "response_saved":
                raise KeyboardInterrupt()
        client = MockAnnotationClient()
        with self.assertRaises(KeyboardInterrupt):
            self.batch(client=client, checkpoint=stop)
        r = self.batch(client=client)
        self.assertEqual((client.calls, r["completed"], r["api_calls"]), (1, 1, 0))
        self.assertTrue(r["results"][0]["recovered_without_request"])

    def test_recovery_never_activates_response_for_changed_input(self):
        def stop(stage, row):
            if stage == "response_saved":
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.batch(checkpoint=stop)
        changed = raw(statement_markdown="You are given three integers. Print their product.")
        r = self.batch([changed])
        self.assertEqual((r["blocked"], r["api_calls"]), (1, 0))

    def test_invalid_response_records_usage_and_blocks_retry(self):
        class Invalid(MockAnnotationClient):
            def call(self, *args, **kwargs):
                self.calls += 1
                return Response("{}", "mock", {"total_tokens": 99}, "stop")
        c = Invalid()
        first = self.batch(client=c)
        second = self.batch(client=c)
        self.assertEqual((c.calls, second["api_calls"]), (1, 0))
        state = Ledger(self.root).records()[0]
        response = Ledger(self.root).artifact("responses", state["attempt_id"])
        self.assertEqual(response["response"]["usage"]["total_tokens"], 99)

    def test_batch_partial_failure_keeps_other_success(self):
        class Partial(MockAnnotationClient):
            def call(self, messages, **kwargs):
                key = json.loads(messages[1]["content"])["problem_key"]
                if key.endswith("_0"):
                    self.calls += 1
                    raise CallError("api_configuration_error", fatal=True)
                return super().call(messages, **kwargs)
        r = self.batch([raw(0), raw(1)], client=Partial())
        self.assertEqual((r["blocked"], r["completed"], r["api_calls"]), (1, 1, 2))
        self.assertEqual(Repository(self.root).manager().get_effective_tags(raw(1)["problem_key"])["specific_tag_ids"], ["enumeration"])

    def test_stale_plan_is_rejected_before_any_claim(self):
        plan = self.plan()
        Repository(self.root).import_records([raw(1)])
        with self.assertRaises(ValueError):
            self.batch(plan=plan)
        self.assertEqual(Ledger(self.root).records(), [])

    def test_plan_integrity_is_checked(self):
        plan = self.plan()
        plan["summary"]["total"] = 900
        with self.assertRaises(ValueError):
            self.batch(plan=plan)

    def test_model_mismatch_in_bound_plan_is_rejected(self):
        plan = bind_plan(self.plan(), "annotation", request_settings(mock_config(model="other-model")))
        with self.assertRaises(ValueError):
            self.batch(plan=plan)

    def test_live_requires_explicit_execute_and_bound_plan(self):
        client, transport = self.client()
        r = execute_batch([raw()], "annotation", root=self.root, config=self.cfg, client=client,
                          cache_roots=[], manifest_roots=[])
        self.assertEqual((r["api_calls"], transport.calls), (0, 0))
        with self.assertRaises(ValueError):
            execute_batch([raw()], "annotation", root=self.root, config=self.cfg, execute=True, client=client)

    def test_live_transport_gate_allows_only_guarded_dispatch(self):
        client, transport = self.client()
        r = self.live_simulation(client)
        self.assertEqual((r["completed"], transport.calls), (1, 1))

    def test_direct_client_call_is_blocked_without_network(self):
        client, transport = self.client()
        with self.assertRaises(CallError):
            client.call([])
        self.assertEqual(transport.calls, 0)

    def test_direct_sdk_call_is_blocked_by_http_hook(self):
        client, transport = self.client()
        with self.assertRaises(Exception):
            client.sdk.chat.completions.create(model=self.cfg.model, messages=[])
        self.assertEqual(transport.calls, 0)

    def test_permit_cannot_be_used_for_a_second_http_request(self):
        client, transport = self.client()
        original = client.call
        errors = []
        def twice(messages, **kwargs):
            result = original(messages, **kwargs)
            try:
                original(messages, **kwargs)
            except ValueError:
                errors.append("blocked")
            return result
        client.call = twice
        self.assertEqual(self.live_simulation(client)["completed"], 1)
        self.assertEqual((transport.calls, errors), (1, ["blocked"]))

    def test_persistent_state_is_checked_in_http_hook(self):
        # Change a manual override after the client-level gate, before the HTTP-level gate.
        def manual_change(request):
            Repository(self.root).manager().change(raw()["problem_key"], "add", ["prefix_sum"])
        client, transport = self.client(hooks=[manual_change])
        r = self.live_simulation(client)
        self.assertEqual((r["blocked"], transport.calls), (1, 0))

    def test_wrong_origin_request_is_rejected_at_transport_hook(self):
        def change_url(request):
            request.url = httpx.URL("https://other.invalid/v1/chat/completions")
        client, transport = self.client(hooks=[change_url])
        self.live_simulation(client)
        self.assertEqual(transport.calls, 0)

    def test_sdk_and_application_retries_are_zero(self):
        client, transport = self.client()
        self.assertEqual(client.sdk.max_retries, 0)
        with self.assertRaises(ValueError):
            execute_batch([raw()], "annotation", root=self.root, config=mock_config(max_retries=1), execute=True)

    def test_old_real_runner_defaults_to_guarded_dry_run(self):
        path = self.base / "input.json"
        path.write_text(json.dumps([raw()]), encoding="utf-8")
        client, transport = self.client()
        r = run(path, self.cfg, client=client, data_root=self.root)
        self.assertEqual((r["api_calls"], transport.calls), (0, 0))

    def test_old_real_translation_defaults_to_guarded_dry_run(self):
        client, transport = self.client()
        result = translate(normalize(raw()), root=self.root, config=self.cfg, client=client)
        self.assertEqual((result["api_calls"], transport.calls), (0, 0))

    def test_old_cli_execute_without_plan_is_blocked_before_loading_credentials(self):
        path = self.base / "input.json"
        path.write_text(json.dumps([raw()]), encoding="utf-8")
        with patch("execute_processing.Config.from_args", side_effect=AssertionError("No credential loading")), redirect_stdout(io.StringIO()):
            self.assertEqual(annotate_api.main(["--input", str(path), "--execute"]), 2)
            self.assertEqual(translate_api.main(["--input", str(path), "--execute"]), 2)

    def test_mock_cli_does_not_load_dotenv(self):
        source = self.base / "input.json"
        source.write_text(json.dumps([raw()]), encoding="utf-8")
        with patch("execute_processing.Config.from_args", side_effect=AssertionError("No credentials")), redirect_stdout(io.StringIO()):
            self.assertEqual(execute_processing.main(["--input", str(source), "--task", "annotation", "--mock", "--data-root", str(self.root)]), 0)

    def test_mock_cannot_write_production_root(self):
        with self.assertRaises(ValueError):
            execute_batch([raw()], "annotation", mock=True)

    def test_mock_and_live_roots_cannot_be_mixed(self):
        self.batch()
        client, _ = self.client()
        with self.assertRaises(ValueError):
            self.live_simulation(client)

    def test_pdf_and_empty_sources_are_not_dispatched(self):
        r = self.batch([raw(statement_markdown=""), {"platform": "atcoder", "contest_id": "offline", "problem_id": "offline_pdf",
                                                   "problem_name": "Mock PDF", "statement_pdf": "sample.pdf"}])
        self.assertEqual((r["blocked"], r["api_calls"]), (2, 0))

    def test_duplicate_identity_never_generates_two_requests(self):
        r = self.batch([raw(), raw()])
        self.assertEqual(r["api_calls"], 1)

    def test_conflicting_duplicate_identity_does_not_generate(self):
        r = self.batch([raw(), raw(title="Conflict")])
        self.assertEqual(r["api_calls"], 0)

    def test_unknown_legacy_cache_blocks_generation(self):
        cache = self.base / "cache"
        cache.mkdir()
        (cache / "unknown.json").write_text('{"state":"unknown_delivery"}', encoding="utf-8")
        r = execute_batch([raw()], "annotation", root=self.root, mock=True, cache_roots=[cache], manifest_roots=[])
        self.assertEqual((r["blocked"], r["api_calls"]), (1, 0))

    def test_validated_legacy_cache_is_reused(self):
        from test_processing_plan import annotation
        cache = self.base / "cache"
        cache.mkdir()
        (cache / "success.json").write_text(json.dumps({"state": "success", "merged": annotation(raw())}), encoding="utf-8")
        r = execute_batch([raw()], "annotation", root=self.root, mock=True, cache_roots=[cache], manifest_roots=[])
        self.assertEqual((r["reused"], r["api_calls"]), (1, 0))

    def test_corrupt_result_never_triggers_paid_replacement(self):
        self.batch()
        row = Ledger(self.root).records()[0]
        Ledger(self.root).path("results", row["task_id"]).write_text("{}", encoding="utf-8")
        r = self.batch()
        self.assertEqual((r["blocked"], r["api_calls"]), (1, 0))

    def test_limit_is_applied_before_dispatch(self):
        self.assertEqual(self.batch([raw(0), raw(1)], limit=1)["api_calls"], 1)

    def test_ledger_and_paid_results_survive_backup_restore(self):
        self.batch()
        backup = create_backup(self.root, self.base / "backups")["backup"]
        restored = restore_backup(backup, self.base / "isolated", active_root=self.root)["restored_data_root"]
        r = execute_batch([raw()], "annotation", root=restored, mock=True, cache_roots=[], manifest_roots=[])
        self.assertEqual((r["api_calls"], r["reused"]), (0, 1))

    def test_uncertain_state_survives_backup_restore(self):
        def stop(stage, row):
            if stage == "dispatched":
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.batch(checkpoint=stop)
        backup = create_backup(self.root, self.base / "backups")["backup"]
        restored = restore_backup(backup, self.base / "isolated", active_root=self.root)["restored_data_root"]
        r = execute_batch([raw()], "annotation", root=restored, mock=True, cache_roots=[], manifest_roots=[])
        self.assertEqual((r["api_calls"], r["blocked"]), (0, 1))

    def test_credentials_never_enter_execution_files(self):
        self.batch()
        for path in self.root.rglob("*.json"):
            self.assertNotIn(self.cfg.api_key, path.read_text(encoding="utf-8"))

    def test_completed_task_with_changed_model_requires_review(self):
        self.batch()
        result = execute_batch([raw()], "annotation", root=self.root, mock=True, config=mock_config(model="another-model"),
                               cache_roots=[], manifest_roots=[])
        self.assertEqual((result["blocked"], result["api_calls"]), (1, 0))

    def test_direct_executor_cannot_bypass_bound_plan(self):
        executor = Executor(self.root, config=self.cfg, execute=True, cache_roots=[], manifest_roots=[])
        with self.assertRaises(ValueError):
            executor.one(normalize(raw()), "annotation")
        self.assertEqual(Ledger(self.root).records(), [])

    def test_translation_uses_same_live_transport_gate(self):
        def translation_response(request):
            data = json.loads(request.content)
            response = MockTranslationClient().call(data["messages"])
            return httpx.Response(200, json={"id": "offline", "object": "chat.completion", "created": 0,
                "model": "memory-translation", "choices": [{"index": 0, "finish_reason": "stop", "message": {
                    "role": "assistant", "content": response.content}}]})
        client, transport = self.client(MemoryTransport(translation_response))
        for expected in (1, 0):
            plan = bind_plan(self.plan(), "translation", request_settings(self.cfg))
            result = execute_batch([raw()], "translation", root=self.root, config=self.cfg, execute=True,
                                   client=client, plan=plan, cache_roots=[], manifest_roots=[])
            self.assertEqual(result["api_calls"], expected)
        self.assertEqual(transport.calls, 1)

    def test_normalized_body_hash_corruption_never_dispatches(self):
        p = normalize(raw())
        p["original_statement"] += " changed without recomputing hashes"
        result = self.batch([p])
        self.assertEqual((result["blocked"], result["api_calls"]), (1, 0))

    def test_manual_change_while_response_in_flight_is_preserved(self):
        base = MockAnnotationClient()
        root = self.root
        class EditDuringResponse:
            def call(self, *args, **kwargs):
                response = base.call(*args, **kwargs)
                Repository(root).manager().change(raw()["problem_key"], "remove", ["enumeration"])
                return response
        result = self.batch(client=EditDuringResponse())
        self.assertEqual(result["api_calls"], 1)
        manager = Repository(self.root).manager()
        view = manager.get_effective_tags(raw()["problem_key"])
        self.assertNotIn("enumeration", view["specific_tag_ids"])
        self.assertEqual(len(manager.journal.read()[0]), 1)

    def test_source_edit_at_http_hook_prevents_transport(self):
        def change_source(request):
            Repository(self.root).import_records([raw(title="Edited before sending")])
        client, transport = self.client(hooks=[change_source])
        result = self.live_simulation(client)
        self.assertEqual((result["blocked"], transport.calls), (1, 0))

    def test_wire_parameter_edit_is_rejected_at_http_hook(self):
        def change_body(request):
            data = json.loads(request.content)
            data["model"] = "unapproved-model"
            request._content = json.dumps(data).encode()
        client, transport = self.client(hooks=[change_body])
        self.live_simulation(client)
        self.assertEqual(transport.calls, 0)

    def test_unknown_ledger_fields_block_backup_and_execution(self):
        self.batch()
        ledger = Ledger(self.root)
        row = ledger.records()[0]
        row["unreviewed_configuration"] = {"value": "do not archive"}
        ledger.path("tasks", row["task_id"]).write_text(json.dumps(row), encoding="utf-8")
        with self.assertRaises(ValueError):
            create_backup(self.root, self.base / "backups")
        with self.assertRaises(ValueError):
            self.batch()

    def test_completed_missing_catalog_is_not_automatically_replaced(self):
        self.batch()
        (self.root / "catalog/current.json").unlink()  # Synthetic data loss only.
        result = self.batch()
        self.assertEqual((result["blocked"], result["api_calls"]), (1, 0))

    def test_saved_response_with_changed_parameters_is_not_resent(self):
        def stop(stage, row):
            if stage == "response_saved":
                raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            self.batch(checkpoint=stop)
        result = execute_batch([raw()], "annotation", root=self.root, mock=True, config=mock_config(max_output_tokens=12),
                               cache_roots=[], manifest_roots=[])
        self.assertEqual((result["blocked"], result["api_calls"]), (1, 0))


class ExecutionProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="acm-process-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "labels"
        self.worker = Path(__file__).with_name("execution_worker.py")

    def launch(self, role):
        child = subprocess.Popen([sys.executable, "-B", "-X", "utf8", str(self.worker), str(self.root), role],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.addCleanup(lambda: child.poll() is None and child.kill())
        return child

    def finish(self, child):
        out, err = child.communicate(timeout=25)
        self.assertEqual(child.returncode, 0, err)
        return json.loads(out)

    def test_two_processes_cannot_claim_same_task(self):
        first = self.launch("hold")
        deadline = time.monotonic() + 10
        while not (self.base / "claimed.signal").exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.base / "claimed.signal").exists())
        second = self.finish(self.launch("normal"))
        (self.base / "release.signal").touch()
        primary = self.finish(first)
        self.assertEqual((primary["api_calls"], second["api_calls"], second["blocked"]), (1, 0, 1))

    def test_actual_process_exit_before_dispatch_can_retry(self):
        crashed = self.launch("crash_claimed")
        crashed.communicate(timeout=15)
        self.assertEqual(crashed.returncode, 17)
        recovered = self.finish(self.launch("normal"))
        self.assertEqual((recovered["api_calls"], recovered["completed"]), (1, 1))

    def test_actual_process_exit_after_dispatch_never_resends(self):
        crashed = self.launch("crash_dispatched")
        crashed.communicate(timeout=15)
        self.assertEqual(crashed.returncode, 17)
        self.assertEqual(self.finish(self.launch("normal"))["api_calls"], 0)
        self.assertEqual(Ledger(self.root).records()[0]["state"], "uncertain")

    def test_actual_process_exit_with_response_recovers_for_free(self):
        crashed = self.launch("crash_response_saved")
        crashed.communicate(timeout=15)
        self.assertEqual(crashed.returncode, 17)
        recovered = self.finish(self.launch("normal"))
        self.assertEqual((recovered["completed"], recovered["api_calls"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
