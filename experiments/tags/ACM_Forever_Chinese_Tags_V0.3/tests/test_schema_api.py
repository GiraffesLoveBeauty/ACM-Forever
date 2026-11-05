import json
import unittest
from api_helpers import sample, wire
from annotation_api.adapter import adapt
from annotation_api.schema import validate, SCHEMA
from label_pipeline import merge_one


class SchemaTests(unittest.TestCase):
    def test_valid_ids_and_empty_tags(self):
        item = adapt(sample())
        for changes in ({}, {"specific_tag_ids": [], "provisional_tag_ids": ["pending_dp"]},
                        {"specific_tag_ids": [], "provisional_tag_ids": []}):
            self.assertIsInstance(validate(json.dumps(wire(item["rule_base"], **changes)), item), dict)

    def test_illegal_labels_or_extra_fields(self):
        item = adapt(sample())
        for changes in ({"specific_tag_ids": ["new_tag"]}, {"specific_tag_ids": ["pending_dp"]},
                        {"provisional_tag_ids": ["dsu"]}, {"confidence": .99}, {"reason": " "},
                        {"content_hash": "wrong"}, {"problem_key": "wrong"}, {"reason": 5}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate(json.dumps(wire(item["rule_base"], **changes)), item)

    def test_unavailable_editorial_claim_rejected(self):
        item = adapt(sample())
        with self.assertRaises(ValueError):
            validate(json.dumps(wire(item["rule_base"], evidence_kind="official_editorial")), item)

    def test_cf_resolution_keeps_exact_and_other_provisional(self):
        item = adapt(sample("codeforces", tags=["dsu", "dp", "data structures"]))
        pred = validate(json.dumps(wire(item["rule_base"], specific_tag_ids=[], resolved_cf_hints=[
            {"hint": "data structures", "specific_tag_ids": ["segment_tree"]}])), item)
        result = merge_one(item["rule_base"], pred)
        self.assertEqual(result["specific_tag_ids"], ["dsu", "segment_tree"])
        self.assertEqual(result["provisional_tag_ids"], ["pending_dp"])

    def test_cf_unresolved_preserves_provisional(self):
        item = adapt(sample("codeforces", tags=["greedy", "data structures"]))
        result = merge_one(item["rule_base"], validate(json.dumps(wire(item["rule_base"], specific_tag_ids=[])), item))
        self.assertEqual(result["specific_tag_ids"], ["greedy"])
        self.assertEqual(result["provisional_tag_ids"], ["pending_data_structures"])

    def test_invalid_cf_resolutions(self):
        for platform in ("atcoder", "codeforces"):
            item = adapt(sample(platform, tags=["dp"]))
            cases = [[{"hint": "dp", "specific_tag_ids": []}],
                     [{"hint": "graphs", "specific_tag_ids": ["dsu"]}],
                     [{"hint": "dp", "specific_tag_ids": ["prefix_sum"]}] * 2]
            if platform == "atcoder":
                cases.append([{"hint": "dp", "specific_tag_ids": ["prefix_sum"]}])
            for resolution in cases:
                with self.subTest(platform=platform, resolution=resolution), self.assertRaises(ValueError):
                    validate(json.dumps(wire(item["rule_base"], resolved_cf_hints=resolution)), item)

    def test_duplicate_json_properties_rejected(self):
        with self.assertRaises(ValueError):
            validate('{"reason":"a","reason":"b"}', adapt(sample()))

    def test_strict_schema_all_objects_closed(self):
        def walk(value):
            if isinstance(value, dict):
                if value.get("type") == "object":
                    self.assertFalse(value["additionalProperties"])
                    self.assertEqual(set(value["required"]), set(value["properties"]))
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(SCHEMA)
