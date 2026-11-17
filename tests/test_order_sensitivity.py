import unittest

from experiments.order_sensitivity import (
    build_request, read_probe, summarize, total_variation, validate_response,
)
from run_example import ROOT, read_examples


def response(a, b, choice=None):
    probabilities = {"a": a, "b": b}
    return {"answers": {"route": {"type": "choice", "probabilities": probabilities,
        "choice": choice or max(probabilities, key=probabilities.get)}}}


def record(index, a, b, kind="permutation"):
    return {"case_id": "one", "order_index": index, "kind": kind,
            "status": "ok", "response": response(a, b)}


class OrderProbeTests(unittest.TestCase):
    def test_probabilities_are_aligned_by_id(self):
        self.assertAlmostEqual(total_variation({"a": .8, "b": .2},
            {"b": .7, "a": .3}, ["a", "b"]), .5)

    def test_changed_choice_and_repeat_are_counted_separately(self):
        calls = [record(0, .8, .2), record(1, .3, .7),
                 record(2, .8, .2, "canonical_repeat")]
        result = summarize(calls, [{"id": "one", "state": "text"}], ["a", "b"], 2)
        self.assertEqual(result["cases_with_observed_choice_change"], 1)
        self.assertEqual(result["changed_noncanonical_choices"], 1)
        self.assertEqual(result["valid_noncanonical_comparisons"], 1)
        self.assertEqual(result["repeat_choice_agreements"], 1)
        self.assertAlmostEqual(result["max_order_tv"], .5)
        self.assertEqual(result["max_repeat_tv"], 0)

    def test_failure_is_retained_and_cannot_count_as_stability(self):
        calls = [record(0, .8, .2), {"case_id": "one", "order_index": 1,
            "kind": "permutation", "status": "error"}]
        result = summarize(calls, [{"id": "one", "state": "text"}], ["a", "b"], 2)
        self.assertEqual(result["planned_noncanonical_comparisons"], 1)
        self.assertEqual(result["valid_noncanonical_comparisons"], 0)
        self.assertEqual(result["invalid_calls"], 1)
        self.assertEqual(result["complete_cases"], 0)
        self.assertIsNone(result["cases"][0]["stable_across_all_orders"])
        self.assertIsNone(result["changed_choice_fraction_of_valid_comparisons"])

    def test_failed_canonical_cannot_be_replaced_by_another_order(self):
        calls = [{"case_id": "one", "order_index": 0, "kind": "permutation", "status": "error"},
                 record(1, .3, .7), record(2, .3, .7, "canonical_repeat")]
        result = summarize(calls, [{"id": "one", "state": "text"}], ["a", "b"], 2)
        self.assertIsNone(result["cases"][0]["canonical_choice"])
        self.assertEqual(result["valid_noncanonical_comparisons"], 0)
        self.assertEqual(result["repeat_valid_pairs"], 0)

    def test_duplicate_order_indices_do_not_look_complete(self):
        result = summarize([record(0, .8, .2), record(0, .8, .2)],
                           [{"id": "one", "state": "text"}], ["a", "b"], 2)
        self.assertEqual(result["complete_cases"], 0)

    def test_bad_response_is_rejected(self):
        for invalid in [response(float("nan"), .2), response(.8, .8), response(.8, .2, "b")]:
            with self.assertRaises(ValueError):
                validate_response(invalid, ["a", "b"])
        with self.assertRaises(ValueError):
            validate_response(response(.8, .2), ["a", "missing"])

    def test_probe_metadata_and_original_teaching_examples_are_not_sent(self):
        data = read_probe(ROOT / "data/order_probe_v1.json")
        teaching = read_examples(ROOT / "examples.json")
        self.assertFalse({c["state"] for c in data["cases"]} & {c["state"] for c in teaching["examples"]})
        order = list(reversed(data["criteria"]))
        request = build_request(data, data["cases"][0], order)
        self.assertEqual(set(request), {"state", "questions"})
        self.assertEqual(list(request["questions"]["route"]["criteria"]), order)
        self.assertEqual(set(request["questions"]["route"]), {"type", "instructions", "criteria"})
        self.assertNotIn("scenario_tag", request)


if __name__ == "__main__":
    unittest.main()
