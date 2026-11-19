import unittest

from experiments.clarification_thresholds import analyze_thresholds
from experiments.prompt_ablation import CLARIFY


class ClarificationThresholdTests(unittest.TestCase):
    def test_equal_scores_move_together_and_previous_department_error_is_separate(self):
        cases = [
            {"id": "ask", "gold": CLARIFY, "department": "billing", "p_clarification": .30},
            {"id": "bill", "gold": "billing", "department": "billing", "p_clarification": .30},
            {"id": "miss", "gold": "delivery", "department": "technical", "p_clarification": .40},
            {"id": "tech", "gold": "technical", "department": "technical", "p_clarification": .10},
        ]
        analysis = analyze_thresholds(cases)
        rows = analysis["thresholds"]
        self.assertEqual([row["threshold"] for row in rows], [None, .40, .30, .10])
        self.assertEqual([(row["recovered_clarifications"], row["retained_correct_routes"],
                           row["false_clarifications"], row["wrong_department"]) for row in rows],
                         [(0, 2, 0, 1), (0, 2, 1, 0), (1, 1, 2, 0), (1, 0, 3, 0)])
        self.assertEqual(analysis["goals"]["recover_all"], rows[2])
        self.assertEqual(analysis["goals"]["preserve_all"], rows[0])
        self.assertFalse(analysis["goals"]["both_possible"])

    def test_separated_scores_allow_both_goals(self):
        cases = [
            {"id": "ask", "gold": CLARIFY, "department": "delivery", "p_clarification": .40},
            {"id": "deliver", "gold": "delivery", "department": "delivery", "p_clarification": .39},
        ]
        goals = analyze_thresholds(cases)["goals"]
        self.assertTrue(goals["both_possible"])
        self.assertEqual(goals["recover_all"], goals["preserve_all"])
        self.assertEqual(goals["recover_all"]["correct"], 2)
