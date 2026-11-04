"""Synthetic sample contracts and the real backend parser, with no network."""
import json
import unittest
from copy import deepcopy

from annotation_api.adapter import adapt
from annotation_api.prompt import messages
from problem_processing.adapter import normalize
from problem_processing.statement import parser_module
from problem_processing.translation import language_plan, prepare_request


def source(**values):
    return {"platform": "atcoder", "contest_id": "offline", "problem_id": "offline_a",
            "problem_name": "Synthetic Sample Contract",
            "problem_url": "https://atcoder.jp/contests/offline/tasks/offline_a",
            "statement_text": "You are given an integer. Print a valid sequence.",
            "last_fetch_status": "ok", "samples": [], **values}


def omitted(**values):
    return {"index": 1, "input": "1\n", "output": None,
            "output_note": "出力は膨大な量になるため記載しません。", **values}


class SampleContractTests(unittest.TestCase):
    def test_omitted_output_preserves_null_and_note(self):
        sample = omitted()
        result = normalize(source(samples=[sample]))
        self.assertEqual(result["samples"], [sample])
        self.assertEqual(result["processing_status"], "ready")
        self.assertIn("output omitted by source", result["original_statement"])
        self.assertIn("not expected output", result["original_statement"])
        self.assertNotIn("```\nNone", result["original_statement"])
        self.assertNotIn("```\nnull", result["original_statement"])

    def test_backend_parser_to_adapter_without_intermediate_rewriting(self):
        raw = ('<div id="task-statement"><span class="lang-ja">'
               '<h3>問題文</h3><p>Synthetic sequence.</p>'
               '<h3>入力例 1</h3><pre>1\n</pre><h3>出力例 1</h3>'
               '<p>出力は膨大な量になるため記載しません。最小のコストは約 12 です。</p>'
               '</span></div>').encode("utf-8")
        parsed = parser_module().parse_atcoder(raw, source()["problem_url"])
        result = normalize(source(**parsed))
        self.assertIsNone(result["samples"][0]["output"])
        self.assertEqual(result["samples"], parsed["samples"])
        self.assertEqual(result["processing_status"], "ready")

    def test_sql_samples_json_roundtrip(self):
        row = source(samples=json.dumps([omitted()]), sample_count=1)
        self.assertEqual(normalize(row)["samples"], [omitted()])

    def test_absent_output_is_not_an_omission(self):
        sample = omitted()
        del sample["output"]
        with self.assertRaises(ValueError):
            normalize(source(samples=[sample]))

    def test_null_output_requires_explicit_nonempty_note(self):
        for value in (None, "", " \r\n", 12, [], True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize(source(samples=[omitted(output_note=value)]))

    def test_null_output_without_note_rejected(self):
        sample = omitted()
        del sample["output_note"]
        with self.assertRaises(ValueError):
            normalize(source(samples=[sample]))

    def test_empty_string_is_valid_output_not_omission(self):
        result = normalize(source(samples=[{"index": 1, "input": "", "output": ""}]))
        self.assertEqual(result["samples"][0]["output"], "")
        self.assertNotIn("output omitted by source", result["original_statement"])

    def test_explicit_no_input_is_retained(self):
        result = normalize(source(samples=[omitted(input="")]))
        self.assertEqual(result["samples"][0]["input"], "")

    def test_nonstring_outputs_and_inputs_rejected(self):
        for field, value in (("output", 1), ("output", False), ("output", []), ("input", None)):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                normalize(source(samples=[omitted(**{field: value})]))

    def test_duplicate_indices_and_wrong_count_rejected(self):
        for samples, count in (([omitted(), omitted()], 2), ([omitted()], 0), ([omitted()], True)):
            with self.subTest(count=count), self.assertRaises(ValueError):
                normalize(source(samples=samples, sample_count=count))

    def test_nonarray_samples_rejected_even_when_falsy(self):
        for samples in (False, 0, "", {}):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                normalize(source(samples=samples))

    def test_note_and_samples_newlines_normalized_without_source_mutation(self):
        row = source(samples=[omitted(input=" 1\r\n\r\n", output_note="First\r\nSecond")])
        before = deepcopy(row)
        result = normalize(row)
        self.assertEqual(row, before)
        self.assertEqual(result["samples"][0]["input"], " 1\n\n")
        self.assertEqual(result["samples"][0]["output_note"], "First\nSecond")

    def test_omission_roundtrip_and_order_are_idempotent(self):
        samples = [omitted(index=2), {"index": 1, "input": "1", "output": "2"}]
        first = normalize(source(samples=samples))
        self.assertEqual(first, normalize(source(samples=list(reversed(samples)))))
        self.assertEqual(first, normalize(json.loads(json.dumps(first))))
        self.assertEqual(first["original_statement"].count("output omitted by source"), 1)

    def test_note_change_invalidates_both_task_inputs(self):
        first = normalize(source(samples=[omitted()]))
        changed = normalize(source(samples=[omitted(output_note="A different omission note.")]))
        for name in ("normalized_content_hash", "annotation_input_hash", "translation_input_hash"):
            self.assertNotEqual(first[name], changed[name])

    def test_note_crlf_does_not_invalidate_inputs(self):
        first = normalize(source(samples=[omitted(output_note="First\r\nSecond")]))
        other = normalize(source(samples=[omitted(output_note="First\nSecond")]))
        for name in ("normalized_content_hash", "annotation_input_hash", "translation_input_hash"):
            self.assertEqual(first[name], other[name])

    def test_annotation_and_translation_receive_omission_context(self):
        result = normalize(source(samples=[omitted(output_note="Output is omitted because it is very long.")]))
        user = json.loads(messages(adapt(result))[1]["content"])
        self.assertIn("not expected output", user["statement_markdown"])
        plan = language_plan(result)
        self.assertIn("Output is omitted", plan["source_text"])
        prepared = prepare_request(result, plan)
        self.assertTrue(prepared["segments"])

    def test_normalized_reimport_rejects_invalid_sample_metadata(self):
        result = normalize(source(samples=[omitted()]))
        result["samples"][0]["output_note"] = ""
        with self.assertRaises(ValueError):
            normalize(result)

    def test_generated_note_marker_does_not_skip_english_translation(self):
        result = normalize(source(statement_text="Print a valid sequence.", samples=[omitted(output_note="Output omitted.")]))
        plan = language_plan(result)
        self.assertEqual(plan["action"], "translate")
        self.assertEqual(plan["source_language"], "en")

    def test_normalized_reimport_rejects_changed_note_without_body_update(self):
        result = normalize(source(samples=[omitted()]))
        result["samples"][0]["output_note"] = "Different otherwise valid note."
        with self.assertRaises(ValueError):
            normalize(result)

    def test_note_for_nonnull_output_is_context_not_answer(self):
        result = normalize(source(samples=[omitted(output="3\n", output_note="A synthetic explanation.")]))
        self.assertIn("```\n3\n```", result["original_statement"])
        self.assertIn("> A synthetic explanation.", result["original_statement"])
        self.assertEqual(result, normalize(result))

    def test_local_collector_raw_hash_alias_is_preserved(self):
        result = normalize(source(sha256="a" * 64, requested_language="en"))
        self.assertEqual(result["source_statement_sha256"], "a" * 64)
        self.assertNotEqual(result["normalized_content_hash"], "a" * 64)

    def test_raw_hash_alias_conflict_or_invalid_value_rejected(self):
        for values in ({"sha256": "invalid"}, {"sha256": "a" * 64, "statement_sha256": "b" * 64}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                normalize(source(**values))

    def test_raw_hash_aliases_compare_case_insensitively(self):
        result = normalize(source(sha256="A" * 64, statement_sha256="a" * 64))
        self.assertEqual(result["source_statement_sha256"], "a" * 64)


if __name__ == "__main__":
    unittest.main()
