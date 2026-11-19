import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from evaluation import ReviewPending
from experiments.two_stage_routing import HOLDOUT_LOCAL, HOLDOUT_QUEUE, main, route_two_stage, stage_prompts
from review_cases import DEFAULT_POLICY
from task_policy import load_policy


def choice_response(winner, candidates):
    return {"answers": {"route": {
        "type": "choice",
        "choice": winner,
        "probabilities": {key: float(key == winner) for key in candidates},
    }}}


class TwoStageRoutingTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_policy(DEFAULT_POLICY)
        self.prompts = stage_prompts(self.policy)
        self.state = "The settings screen is blank."
        self.gate = ["route_to_team", "needs_clarification"]
        self.departments = ["billing", "technical", "delivery"]

    def test_clarification_first_changes_only_gate_candidate_order(self):
        reversed_gate = stage_prompts(self.policy, gate_order="clarification-first")
        self.assertEqual(list(self.prompts["gate"]["criteria"]), self.gate)
        self.assertEqual(list(reversed_gate["gate"]["criteria"]), list(reversed(self.gate)))
        self.assertEqual(reversed_gate, self.prompts)
        self.assertEqual(list(reversed_gate["department"]["criteria"]),
                         list(self.prompts["department"]["criteria"]))

    def test_clarification_ends_after_first_call(self):
        predict = Mock(return_value=choice_response("needs_clarification", self.gate))
        result = route_two_stage(predict, self.prompts, self.state)
        predict.assert_called_once()
        self.assertEqual((result["status"], result["choice"], result["model_calls"]),
                         ("ok", "needs_clarification", 1))
        self.assertEqual([call["stage"] for call in result["raw_calls"]], ["gate"])

    def test_frozen_cutoff_is_inclusive_and_preserves_the_raw_gate_response(self):
        for score, expected, calls in [(.26, "needs_clarification", 1), (.2599999, "technical", 2)]:
            with self.subTest(score=score):
                gate = choice_response("route_to_team", self.gate)
                gate["answers"]["route"]["probabilities"] = {
                    "route_to_team": 1 - score, "needs_clarification": score,
                }
                predict = Mock(side_effect=[gate, choice_response("technical", self.departments)])
                result = route_two_stage(predict, self.prompts, self.state, clarification_threshold=.26)
                self.assertEqual((result["status"], result["choice"], predict.call_count), ("ok", expected, calls))
                self.assertEqual(result["raw_calls"][0]["response"]["answers"]["route"]["choice"],
                                 "route_to_team")
                self.assertEqual(result["raw_calls"][0]["threshold_decision"],
                                 "route_to_team" if calls == 2 else "needs_clarification")

    def test_holdout_waits_for_complete_review_before_creating_outputs_or_loading_model(self):
        with TemporaryDirectory() as tmp, patch("experiments.two_stage_routing.load_reviewed_cases",
                side_effect=ReviewPending("Review pending")) as review, patch(
                "experiments.two_stage_routing.load_local_model") as loader, redirect_stdout(StringIO()):
            out = Path(tmp) / "pending"
            self.assertEqual(main(["--holdout", "--output-dir", str(out)]), 2)
            review.assert_called_once_with(HOLDOUT_QUEUE, DEFAULT_POLICY, HOLDOUT_LOCAL)
            loader.assert_not_called()
            self.assertFalse(out.exists())

    def test_department_step_receives_original_text_and_three_department_choices(self):
        responses = [choice_response("route_to_team", self.gate),
                     choice_response("technical", self.departments)]
        predict = Mock(side_effect=responses)
        result = route_two_stage(predict, self.prompts, self.state)
        self.assertEqual((result["status"], result["choice"], result["model_calls"]),
                         ("ok", "technical", 2))
        self.assertEqual(predict.call_count, 2)
        self.assertEqual([call["stage"] for call in result["raw_calls"]], ["gate", "department"])
        for index, (stage, candidates) in enumerate([("gate", self.gate),
                                                      ("department", self.departments)]):
            request = predict.call_args_list[index].kwargs
            self.assertEqual(request, {"state": self.state, "questions": {"route": {
                "type": "choice",
                "instructions": self.prompts[stage]["instructions"],
                "criteria": self.prompts[stage]["criteria"],
            }}})
            self.assertEqual(list(request["questions"]["route"]["criteria"]), candidates)
            self.assertEqual(result["raw_calls"][index]["candidate_order"], candidates)
            self.assertEqual(result["raw_calls"][index]["request"], request)
            self.assertEqual(result["raw_calls"][index]["response"], responses[index])
        self.assertEqual(self.prompts["department"]["criteria"],
                         {key: self.policy["criteria"][key] for key in self.departments})

    def test_failed_gate_stops_without_assigning_or_clarifying(self):
        predict = Mock(return_value=choice_response("billing", self.gate))
        result = route_two_stage(predict, self.prompts, self.state)
        predict.assert_called_once()
        self.assertEqual((result["status"], result["choice"], result["model_calls"]),
                         ("error", None, 1))
        self.assertEqual(result["raw_calls"][0]["status"], "error")

    def test_failed_department_step_stays_a_technical_failure(self):
        predict = Mock(side_effect=[choice_response("route_to_team", self.gate),
                                    RuntimeError("simulated inference failure")])
        result = route_two_stage(predict, self.prompts, self.state)
        self.assertEqual(predict.call_count, 2)
        self.assertEqual((result["status"], result["choice"], result["model_calls"]),
                         ("error", None, 2))
        self.assertEqual([call["status"] for call in result["raw_calls"]], ["ok", "error"])


if __name__ == "__main__":
    unittest.main()
