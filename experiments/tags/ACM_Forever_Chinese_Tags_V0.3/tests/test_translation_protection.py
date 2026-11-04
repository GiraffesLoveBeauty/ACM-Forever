"""Synthetic regressions for translation masking and validation; never use live APIs."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from annotation_api.client import Response
from problem_processing.adapter import normalize
from problem_processing.execution_state import Ledger
from problem_processing.executor import Executor, execute_batch, mock_config, task_identity
from problem_processing.planning import task_policies
from problem_processing.translation import (
    MockTranslationClient, TOKEN, TRANSLATION_VERSION, language_plan,
    prepare_request, translation_fingerprint, validate_translation,
)


def problem(text):
    return normalize({"platform": "atcoder", "problem_key": "atcoder:offline:offline_protection",
                      "title": "Synthetic Translation", "statement_markdown": text,
                      "statement_status": "ok", "language_hint": "en"})


class TranslationProtectionTests(unittest.TestCase):
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.create_connection",
                       "httpx.HTTPTransport.handle_request", "annotation_api.client.APIClient.call"):
            guard = patch(target, side_effect=AssertionError("No real network/API permitted"))
            guard.start()
            self.addCleanup(guard.stop)

    def prepare(self, text):
        p = problem(text)
        return prepare_request(p, language_plan(p))

    def payload(self, prepared):
        return json.loads(MockTranslationClient().call(prepared["messages"]).content)

    def validate(self, value, prepared):
        return validate_translation(json.dumps(value, ensure_ascii=False), prepared)

    def test_articles_a_and_A_are_not_variables(self):
        prepared = self.prepare("A train has a car. There is a train consisting of N cars.")
        self.assertEqual(list(prepared["protected"].values()), ["N"])
        self.assertIn("A train has a car.", prepared["segments"][0]["text"])

    def test_first_person_I_is_not_a_variable(self):
        prepared = self.prepare("I have a train. I will count N cars.")
        self.assertEqual(list(prepared["protected"].values()), ["N"])

    def test_possessive_suffix_is_prose_not_a_variable(self):
        prepared = self.prepare("The bird's color changes. Takahashi's birds have N colors.")
        self.assertEqual(list(prepared["protected"].values()), ["N"])

    def test_curly_possessive_suffix_is_prose(self):
        prepared = self.prepare("The bird’s color changes over M days.")
        self.assertEqual(list(prepared["protected"].values()), ["M"])

    def test_contraction_suffixes_are_not_variables(self):
        prepared = self.prepare("Don't change the input. I'm counting N birds. We'd like the result.")
        self.assertEqual(list(prepared["protected"].values()), ["N"])

    def test_quoted_and_explicit_suffix_like_variables_stay_protected(self):
        prepared = self.prepare("Print 's', ‘t’, $s$ and `t` for these integers.")
        self.assertEqual(list(prepared["protected"].values()), ["s", "t", "$s$", "`t`"])

    def test_possessive_can_be_translated_without_residual_s(self):
        prepared = self.prepare("The bird's color is B_i from day 1.")
        token = prepared["movable_tokens"][0]
        value = {"title_zh": "模拟鸟题", "segments": [{"id": 0,
                 "text": f"从第 1 天起，这只鸟的颜色为 {token}。"}]}
        self.assertEqual(self.validate(value, prepared)[1], "从第 1 天起，这只鸟的颜色为 B_i。")

    def test_first_person_past_modal_and_conjunction_are_not_symbols(self):
        prepared = self.prepare("I was on a train. I must count cars. I and a friend count N cars.")
        self.assertEqual(list(prepared["protected"].values()), ["N"])

    def test_output_commands_do_not_turn_articles_into_variables(self):
        prepared = self.prepare("Print a single integer. Output a line. Return a value.")
        self.assertEqual(prepared["protected"], {})

    def test_bare_a_and_A_as_variable_subjects_are_preserved(self):
        prepared = self.prepare("If a is even, print a. A represents the answer.")
        self.assertEqual(list(prepared["protected"].values()), ["a", "a", "A"])

    def test_declared_lowercase_a_and_printed_a_are_protected(self):
        prepared = self.prepare("You are given an integer a. Print a.")
        self.assertEqual(list(prepared["protected"].values()), ["a", "a"])

    def test_article_is_not_inferred_from_a_declaration_elsewhere(self):
        prepared = self.prepare("You are given an integer a. There is a train. Print a.")
        self.assertEqual(list(prepared["protected"].values()), ["a", "a"])
        self.assertIn("a train", prepared["segments"][0]["text"])

    def test_A_and_I_declarations_are_protected(self):
        prepared = self.prepare("You are given integers A and B and an index I. Output I.")
        self.assertEqual(list(prepared["protected"].values()), ["A", "B", "I", "I"])

    def test_explicit_math_code_and_subscripts_protect_ambiguous_symbols(self):
        prepared = self.prepare("Compute $a$, `A`, \\(I\\), a_i and A_j for these values.")
        self.assertEqual(list(prepared["protected"].values()), ["$a$", "`A`", "\\(I\\)", "a_i", "A_j"])

    def test_compound_formula_is_one_immutable_token(self):
        prepared = self.prepare("Compute a + b and N^2 for these integers.")
        self.assertEqual(list(prepared["protected"].values()), ["a + b", "N^2"])
        self.assertEqual(prepared["movable_tokens"], [])

    def test_request_tells_model_which_tokens_can_move(self):
        prepared = self.prepare("Given N and K, print $N-K+1$.")
        request = json.loads(prepared["messages"][1]["content"])
        self.assertEqual(request["movable_tokens"], prepared["movable_tokens"])
        self.assertEqual(len(request["movable_tokens"]), 2)
        self.assertEqual([prepared["protected"][token] for token in request["movable_tokens"]], ["N", "K"])

    def test_chinese_variable_reordering_on_one_line_is_accepted(self):
        prepared = self.prepare("An integer N is selected before another integer K.")
        n, k = prepared["movable_tokens"]
        value = {"title_zh": "模拟题", "segments": [{"id": 0, "text": f"先选另一个整数 {k} 之前，选择整数 {n}。"}]}
        _, statement = self.validate(value, prepared)
        self.assertIn("整数 K", statement)
        self.assertIn("整数 N", statement)
        self.assertNotIn("__ACM_KEEP", statement)

    def test_train_case_has_no_residual_article_a(self):
        prepared = self.prepare("Problem Statement\nThere is a train consisting of N cars.\nFind the K-th car from the front.")
        n, k = prepared["movable_tokens"]
        value = {"title_zh": "模拟车厢题", "segments": [{"id": 0,
                 "text": f"题目描述\n有一列由 {n} 节车厢组成的火车。\n求从前往后第 {k} 节车厢。"}]}
        _, statement = self.validate(value, prepared)
        self.assertNotRegex(statement, r"\ba\b")
        self.assertIn("N 节车厢", statement)
        self.assertEqual(prepared["protection_version"], TRANSLATION_VERSION)

    def test_formula_bytes_and_variable_reorder_within_same_slot(self):
        prepared = self.prepare("Given integers N and K, print $N-K+1$.")
        n, k = prepared["movable_tokens"]
        formula = next(t for t, v in prepared["protected"].items() if v == "$N-K+1$")
        value = {"title_zh": "模拟题", "segments": [{"id": 0, "text": f"给定整数 {k} 和 {n}，输出 {formula}。"}]}
        self.assertIn("$N-K+1$", self.validate(value, prepared)[1])

    def test_variable_cannot_cross_formula_anchor(self):
        prepared = self.prepare("Given integer N, print $K+1$.")
        value = self.payload(prepared)
        self.swap(value, prepared["movable_tokens"][0], next(t for t, v in prepared["protected"].items() if v == "$K+1$"))
        with self.assertRaises(ValueError): self.validate(value, prepared)

    @staticmethod
    def swap(value, first, second):
        for row in value["segments"]:
            row["text"] = row["text"].replace(first, "__SWAP__").replace(second, first).replace("__SWAP__", second)

    def test_formula_tokens_cannot_be_swapped(self):
        prepared = self.prepare("Print $A-B$ and $B-A$ for these values.")
        value = self.payload(prepared)
        self.swap(value, *prepared["protected"])
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_variables_cannot_cross_line_boundaries(self):
        prepared = self.prepare("Print integer N on this line.\nPrint integer K on the next line.")
        value = self.payload(prepared)
        self.swap(value, *prepared["movable_tokens"])
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_variables_cannot_cross_segment_boundaries(self):
        prepared = self.prepare("Print integer N on this line.\n\nPrint integer K on the next line.")
        value = self.payload(prepared)
        self.swap(value, *prepared["movable_tokens"])
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_repeated_variables_are_not_deduplicated(self):
        prepared = self.prepare("Print N and N again for these integers.")
        self.assertEqual(len(prepared["movable_tokens"]), 2)
        value = self.payload(prepared)
        first, second = prepared["movable_tokens"]
        value["segments"][0]["text"] = value["segments"][0]["text"].replace(second, first)
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_missing_duplicated_and_unknown_tokens_rejected(self):
        prepared = self.prepare("Print N and K for these integers.")
        token = prepared["movable_tokens"][0]
        for replacement in ("", token + token, "__ACM_KEEP_999__", "__ACM_KEEP_00__"):
            with self.subTest(replacement=replacement):
                value = self.payload(prepared)
                value["segments"][0]["text"] = value["segments"][0]["text"].replace(token, replacement)
                with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_malformed_token_injection_rejected(self):
        prepared = self.prepare("Print N for these integers.")
        for extra in ("__ACM_KEEP_X__", "__ACM_KEEP_", "__ACM_KEEP"):
            with self.subTest(extra=extra):
                value = self.payload(prepared)
                value["segments"][0]["text"] += extra
                with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_title_cannot_contain_a_placeholder(self):
        prepared = self.prepare("Print N for these integers.")
        value = self.payload(prepared)
        value["title_zh"] = "模拟 __ACM_KEEP_0__"
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_reserved_source_or_title_rejected_before_masking(self):
        for marker in ("__ACM_KEEP_0__", "__ACM_KEEP_bad__"):
            with self.subTest(marker=marker):
                with self.assertRaises(ValueError): self.prepare("Print " + marker)
                p = problem("Print an integer on a line.")
                p["original_title"] = marker
                with self.assertRaises(ValueError): prepare_request(p, language_plan(p))

    def test_code_samples_formulas_links_and_images_restored_exactly(self):
        pieces = ["```cpp\nif (a < b) return a;\n```", "~~~\n1 2\n~~~", "$a+b$",
                  "\\[A < B\\]", "`a[i]`", "[reference](https://example.org/help)", "![figure](https://example.org/a.png)"]
        prepared = self.prepare("Print the required result.\n\n" + "\n\n".join(pieces))
        statement = self.validate(self.payload(prepared), prepared)[1]
        for piece in pieces:
            self.assertIn(piece, statement)
        self.assertFalse(TOKEN.search(statement))

    def test_samples_cannot_be_swapped(self):
        prepared = self.prepare("Print the required result.\n\n```\n1 2\n```\n\n```\n3\n```")
        value = self.payload(prepared)
        self.swap(value, *prepared["protected"])
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_crlf_fenced_code_is_one_anchor_and_restored_byte_for_byte(self):
        code = "```cpp\r\nint a = 1;\r\nreturn a;\r\n```\r\n"
        prepared = self.prepare("Print the required result.\r\n\r\n" + code)
        self.assertEqual(list(prepared["protected"].values()), [code])
        self.assertEqual(prepared["movable_tokens"], [])
        self.assertIn(code, self.validate(self.payload(prepared), prepared)[1])

    def test_links_cannot_be_swapped(self):
        prepared = self.prepare("Read [first](https://example.org/1) before [second](https://example.org/2).")
        value = self.payload(prepared)
        self.swap(value, *prepared["protected"])
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_changed_numbers_markdown_and_segments_still_rejected(self):
        prepared = self.prepare("# Statement\n\nThere are 100 objects.\n\n- Print N objects.")
        original = self.payload(prepared)
        for kind in ("number", "markdown", "drop", "duplicate", "reorder"):
            with self.subTest(kind=kind):
                value = deepcopy(original)
                if kind == "number": value["segments"][1]["text"] = value["segments"][1]["text"].replace("100", "99")
                if kind == "markdown": value["segments"][0]["text"] = value["segments"][0]["text"].replace("#", "##")
                if kind == "drop": value["segments"].pop()
                if kind == "duplicate": value["segments"].append(value["segments"][-1])
                if kind == "reorder": value["segments"].reverse()
                with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_legacy_prepared_without_movable_metadata_remains_strict(self):
        prepared = self.prepare("Print N and K for these integers.")
        value = self.payload(prepared)
        self.swap(value, *prepared["movable_tokens"])
        del prepared["movable_tokens"]
        with self.assertRaises(ValueError): self.validate(value, prepared)

    def test_current_revision_is_in_policy_and_legacy_fingerprints_change(self):
        p = problem("Print integer N for these values.")
        lang = language_plan(p)
        current = translation_fingerprint(p, lang, {"model": "mock"})
        with patch("problem_processing.translation.TRANSLATION_VERSION", "translation-1"):
            self.assertNotEqual(current, translation_fingerprint(p, lang, {"model": "mock"}))
        self.assertEqual(task_policies()["translation"]["revision"], TRANSLATION_VERSION)
        self.assertNotEqual(TRANSLATION_VERSION, "translation-1")

    def test_translation_policy_change_does_not_change_annotation_identity(self):
        p = problem("Print integer N for these values.")
        cfg = mock_config()
        annotation, translation = (task_identity(p, task, cfg) for task in ("annotation", "translation"))
        with patch("problem_processing.translation.SYSTEM", "old translation policy"):
            self.assertEqual(annotation, task_identity(p, "annotation", cfg))
            self.assertNotEqual(translation, task_identity(p, "translation", cfg))

    def test_failed_old_response_stays_blocked_and_is_never_reissued(self):
        class InvalidClient:
            calls = 0
            def call(self, *args, **kwargs):
                self.calls += 1
                return Response('{"title_zh":"模拟","segments":[]}', "mock", {"total_tokens": 5}, "stop")
        with tempfile.TemporaryDirectory() as tmp:
            root, cfg, client = Path(tmp)/"labels", mock_config(), InvalidClient()
            rows = [problem("There is a train with N cars. Print K.")]
            with patch("problem_processing.translation.SYSTEM", "old translation policy"):
                first = execute_batch(rows, "translation", root=root, config=cfg, mock=True,
                                      client=client, cache_roots=[], manifest_roots=[])
            ledger = Ledger(root)
            task = ledger.records()[0]
            before = ledger.path("tasks", task["task_id"]).read_bytes()
            response_before = ledger.path("responses", task["attempt_id"]).read_bytes()
            second = execute_batch(rows, "translation", root=root, config=cfg, mock=True,
                                   client=client, cache_roots=[], manifest_roots=[])
            self.assertEqual((first["blocked"], second["blocked"], client.calls), (1, 1, 1))
            self.assertEqual(second["real_api_calls"], 0)
            self.assertEqual(second["api_calls"], 0)
            self.assertEqual(before, ledger.path("tasks", task["task_id"]).read_bytes())
            self.assertEqual(response_before, ledger.path("responses", task["attempt_id"]).read_bytes())
            self.assertFalse((root/"translations/current.json").exists())
            executor = Executor(root, config=cfg, mock=True, client=client, cache_roots=[], manifest_roots=[])
            with self.assertRaisesRegex(ValueError, "策略已变化"):
                executor._finish(task)
            self.assertEqual(client.calls, 1)


if __name__ == "__main__":
    unittest.main()
