import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation import ReviewPending, load_reviewed_cases, score_predictions
from review_cases import HOLDOUT_PURPOSE, add_review, annotate, load_review_state, prepare_queue, review_status, write_json
from rule_baseline import route_by_rules
from run_evaluation import evaluate_methods, main as evaluation_main
from run_example import ROOT
from task_policy import LABELS, load_policy, policy_hash


class ScoringTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"id": str(i), "gold": label} for i, label in enumerate(LABELS)]

    def test_hand_calculated_confusion_and_fixed_macro_f1(self):
        predictions = [
            {"id": "0", "status": "ok", "choice": "billing"},
            {"id": "1", "status": "ok", "choice": "billing"},
            {"id": "2", "status": "error", "choice": None},
            {"id": "3", "status": "ok", "choice": "needs_clarification"},
        ]
        score = score_predictions(self.cases, predictions)
        self.assertEqual(score["accuracy"], .5)
        self.assertAlmostEqual(score["macro_f1"], 5 / 12)
        self.assertEqual(score["technical_failure_rate"], .25)
        self.assertEqual(score["confusion_matrix"]["delivery"]["__failure__"], 1)
        self.assertEqual(score["per_class"]["needs_clarification"]["tp"], 1)
        self.assertEqual(score["per_class"]["billing"]["fp"], 1)

    def test_missing_prediction_stays_in_denominator(self):
        score = score_predictions(self.cases, [{"id": "0", "status": "ok", "choice": "billing"}])
        self.assertEqual(score["accuracy"], .25)
        self.assertEqual(score["missing_predictions"], 3)
        self.assertEqual(score["technical_failures"], 3)

    def test_duplicate_unknown_and_malformed_predictions_are_rejected(self):
        good = {"id": "0", "status": "ok", "choice": "billing"}
        for predictions in [[good, good], [{**good, "id": "unknown"}],
                            [{**good, "choice": "unknown"}], [{**good, "status": "error"}]]:
            with self.assertRaises(ValueError):
                score_predictions(self.cases, predictions)
        with self.assertRaises(ValueError):
            score_predictions([], [])


class ReviewWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.policy = load_policy(ROOT / "data/task_policy_v1.json")
        self.policy_path = self.base / "policy.json"
        self.queue_path = self.base / "queue.json"
        self.local = self.base / "local"
        write_json(self.policy_path, self.policy)
        source = self.base / "fixture.json"
        write_json(source, {"cases": [
            {"id": "fixture-1", "state": "Please issue an invoice."},
            {"id": "fixture-2", "state": "My password reset link is broken."}]})
        self.queue = prepare_queue(self.policy, [source], {})
        write_json(self.queue_path, self.queue)

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        return load_review_state(self.queue_path, self.policy_path, self.local)

    def complete_fixture_reviews(self):
        _, queue, annotations = self.load()
        for case, label in zip(queue["items"], ["billing", "technical"]):
            add_review(annotations, case, label, "Synthetic unit-test fixture, not a project annotation", "unit-test-fixture")
        write_json(self.local / "annotations.json", annotations)

    def test_queue_has_no_predicted_labels_or_scenario_tags(self):
        for case in self.queue["items"]:
            self.assertIsNone(case["label"])
            self.assertIsNone(case["reason"])
            self.assertNotIn("scenario_tag", case)
            self.assertNotIn("response", case)

    def test_unreviewed_data_blocks_scoring(self):
        with self.assertRaises(ReviewPending):
            load_reviewed_cases(self.queue_path, self.policy_path, self.local)
        self.assertFalse(self.local.exists())

    def test_gate_does_not_load_model_or_create_output(self):
        out = self.base / "scores"
        arguments = ["--policy", str(self.policy_path), "--queue", str(self.queue_path),
                     "--local-dir", str(self.local), "--output-dir", str(out)]
        with patch("run_evaluation.load_local_model") as loader, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(evaluation_main(arguments), 2)
            loader.assert_not_called()
        self.assertFalse(out.exists())

    def test_review_requires_reason_and_does_not_overwrite(self):
        _, queue, annotations = self.load()
        with self.assertRaises(ValueError):
            add_review(annotations, queue["items"][0], "billing", "", "unit-test-fixture")
        add_review(annotations, queue["items"][0], "billing", "fixture", "unit-test-fixture")
        with self.assertRaises(ValueError):
            add_review(annotations, queue["items"][0], "technical", "fixture", "unit-test-fixture")

    def test_one_interactive_review_is_saved_and_resumable(self):
        policy, queue, annotations = self.load()
        answers = iter(["b", "Synthetic test interaction"])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(annotate(policy, queue, annotations, self.local, "unit-test-fixture", 1,
                                      ask=lambda _: next(answers)), 1)
        _, queue, annotations = self.load()
        self.assertEqual(review_status(queue, annotations)["reviewed_cases"], 1)
        self.assertEqual(review_status(queue, annotations)["pending_case_ids"], ["fixture-2"])
        self.assertTrue((self.local / "events.jsonl").is_file())

    def test_holdout_accepts_explicit_label_without_a_written_reason(self):
        self.queue["purpose"] = HOLDOUT_PURPOSE
        write_json(self.queue_path, self.queue)
        policy, queue, annotations = self.load()
        answers = iter(["b", ""])
        with contextlib.redirect_stdout(io.StringIO()):
            annotate(policy, queue, annotations, self.local, "unit-test-fixture", 1, ask=lambda _: next(answers))
        _, _, saved = self.load()
        first = saved["reviews"][0]
        self.assertEqual(first["label"], "billing")
        self.assertEqual(first["assistance"], "user_label_only")
        self.assertIsNone(first["reason"])
        with self.assertRaises(ReviewPending):
            load_reviewed_cases(self.queue_path, self.policy_path, self.local)

    def test_policy_and_text_changes_invalidate_existing_binding(self):
        self.complete_fixture_reviews()
        changed = copy.deepcopy(self.policy)
        changed["instructions"] += " Changed rule."
        write_json(self.policy_path, changed)
        with self.assertRaises(ValueError):
            self.load()
        write_json(self.policy_path, self.policy)
        queue = copy.deepcopy(self.queue)
        queue["items"][0]["state"] += " Changed text."
        write_json(self.queue_path, queue)
        with self.assertRaises(ValueError):
            self.load()

    def test_complete_fixture_runs_rules_only_without_model(self):
        self.complete_fixture_reviews()
        out = self.base / "scores"
        with patch("run_evaluation.load_local_model") as loader, contextlib.redirect_stdout(io.StringIO()):
            status = evaluation_main(["--policy", str(self.policy_path), "--queue", str(self.queue_path),
                "--local-dir", str(self.local), "--methods", "rules", "--output-dir", str(out)])
            self.assertEqual(status, 0)
            loader.assert_not_called()
        scores = json.loads((out / "scores.json").read_text(encoding="utf-8"))
        self.assertEqual(scores["rules"]["accuracy"], 1)
        self.assertTrue((out / "annotations.json").is_file())


class BaselineAndRequestTests(unittest.TestCase):
    def test_rules_handle_words_mixed_and_explicit_primary_clause(self):
        self.assertEqual(route_by_rules("A refund appeared today.")["choice"], "billing")
        self.assertFalse(route_by_rules("A refund appeared today.")["matches"]["technical"])
        self.assertEqual(route_by_rules("A duplicate charge and a login error.")["choice"], "needs_clarification")
        self.assertEqual(route_by_rules("A duplicate charge. Please fix my login first.")["choice"], "technical")
        self.assertEqual(route_by_rules("Please help.")["choice"], "needs_clarification")

    def test_gold_labels_and_review_information_never_reach_model(self):
        captured = []

        def predict(**request):
            captured.append(request)
            keys = list(request["questions"]["route"]["criteria"])
            return {"answers": {"route": {"type": "choice", "choice": "billing",
                "probabilities": {key: .7 if key == "billing" else .1 for key in keys}}}}

        policy = load_policy(ROOT / "data/task_policy_v1.json")
        records, scores = evaluate_methods(predict, policy,
            [{"id": "fixture", "state": "A ticket", "gold": "technical"}], ["single"])
        self.assertEqual(set(captured[0]), {"state", "questions"})
        self.assertEqual(captured[0]["state"], "A ticket")
        self.assertEqual(set(captured[0]["questions"]["route"]), {"type", "instructions", "criteria"})
        self.assertEqual(scores["single"]["accuracy"], 0)
        self.assertNotIn("gold", records[0])

    def test_new_rule_is_bound_to_a_version(self):
        policy = load_policy(ROOT / "data/task_policy_v1.json")
        changed = copy.deepcopy(policy)
        changed["rules_zh"][-1] += " Different wording."
        self.assertNotEqual(policy_hash(policy), policy_hash(changed))
        self.assertIn("primary request", policy["instructions"])


if __name__ == "__main__":
    unittest.main()
