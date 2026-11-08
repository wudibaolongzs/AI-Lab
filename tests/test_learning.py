import json
from pathlib import Path
import unittest
from unittest.mock import patch

from exercise import EXERCISES, HINT_LOCATION, check_submission
from learning import LearningConflict, challenge, verify

SOLUTIONS = {
    "average": "sum(nums) / len(nums)", "sum": "sum(nums)", "count": "len(nums)",
    "double_sum": "sum(nums) * 2", "shifted_average": "sum(nums) / len(nums) + 2",
    "total_with_fee": "sum(nums) + 5", "pair_count": "len(nums) * 2",
    "average_with_zero": "sum(nums) / (len(nums) + 1)",
}
ANSWERS = dict(zip(SOLUTIONS, (4.5, -4, 5, 10, -1, 15, 10, 3)))


def solution(exercise_id):
    return EXERCISES[exercise_id]["signature"] + "\n    return " + SOLUTIONS[exercise_id]


class CurriculumTests(unittest.TestCase):
    def test_eight_correct_solutions_and_buggy_starters(self):
        self.assertTrue(set(SOLUTIONS).issubset(EXERCISES))
        for exercise_id in SOLUTIONS:
            item = EXERCISES[exercise_id]
            with self.subTest(exercise_id=exercise_id):
                self.assertTrue(item["learning_goal"])
                self.assertEqual(check_submission(solution(exercise_id), exercise_id)["status"], "passed")
                self.assertEqual(check_submission(item["starter_code"], exercise_id)["status"], "failed")

    def test_all_exercises_reject_arbitrary_execution(self):
        with patch("builtins.open", side_effect=AssertionError("must not execute")):
            for exercise_id, item in EXERCISES.items():
                code = item["signature"] + "\n    return open('secret')"
                self.assertEqual(check_submission(code, exercise_id)["status"], "invalid")

    def test_new_evaluation_samples_match_observed_diagnoses(self):
        samples = json.loads((Path(__file__).resolve().parents[1] / "evals/curriculum-samples.json").read_text(encoding="utf-8"))
        self.assertEqual(len(samples), 15)
        for sample in samples:
            result = check_submission(sample["code"], sample["exercise"])
            self.assertEqual(result["diagnosis"]["kind"], sample["diagnosis_kind"])
            self.assertEqual(len(result["hints"]), 3)
            self.assertIn(sample["case_id"], [case["id"] for case in result["cases"] if case["status"] != "passed"])


class LearningTests(unittest.TestCase):
    def test_challenges_do_not_disclose_answers(self):
        for exercise_id in EXERCISES:
            if not EXERCISES[exercise_id]["has_transfer"]:
                self.assertFalse(challenge(exercise_id)["available"])
                continue
            self.assertEqual(set(challenge(exercise_id)), {"exercise_id", "question_id", "question", "answer_type"})
            self.assertEqual(challenge(exercise_id)["answer_type"], "number")

    def test_original_failure_requires_conflict(self):
        for exercise_id in ANSWERS:
            with self.assertRaises(LearningConflict):
                verify(exercise_id, EXERCISES[exercise_id]["starter_code"], ANSWERS[exercise_id])

    def test_right_wrong_and_explanation_is_never_scored(self):
        for exercise_id, answer in ANSWERS.items():
            result = verify(exercise_id, solution(exercise_id), answer, "I guessed")
            self.assertTrue(result["correct"])
            self.assertTrue(result["original_passed"])
            self.assertTrue(result["transfer_checked"])
            self.assertTrue(result["explanation_recorded"])
            wrong = verify(exercise_id, solution(exercise_id), answer + 1, "A convincing explanation")
            self.assertFalse(wrong["correct"])
            self.assertFalse(verify(exercise_id, solution(exercise_id), answer)["explanation_recorded"])

    def test_invalid_inputs(self):
        for answer in (True, False, None, "4.5", float("nan"), float("inf"), -float("inf"), 10 ** 400):
            with self.subTest(answer=repr(answer)), self.assertRaises(ValueError):
                verify("average", solution("average"), answer)
        for explanation in (None, [], "x" * 501):
            with self.assertRaises(ValueError):
                verify("average", solution("average"), 4.5, explanation)
        for exercise_id in ("missing", None, []):
            with self.assertRaises(ValueError):
                challenge(exercise_id)
        with self.assertRaises(ValueError):
            verify("average", None, 4.5)
