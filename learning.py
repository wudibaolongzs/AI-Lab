"""Fixed numeric transfer checks, separate from original code acceptance.

No student source is executed by Python or sent to a remote service. Explanations
are optional self-reports; they are never scored as evidence of understanding.
"""
import math

from exercise import EXERCISES, check_submission


class LearningConflict(ValueError):
    """Original exercise has not passed; HTTP adapters should return 409."""


# Answers stay server-side. These inputs are independent of original test cases.
_QUESTIONS = {
    "average": ("avg-transfer-1", "列表总和为 18，共 4 个元素。平均值是多少？", 4.5),
    "sum": ("sum-transfer-1", "[-8, 3, 1] 的总和是多少？", -4),
    "count": ("count-transfer-1", "[0, 0, -9, 2, 2] 有几个元素？", 5),
    "double_sum": ("double-transfer-1", "将 [-3, 8] 中每个值翻倍，新总和是多少？", 10),
    "shifted_average": ("shift-transfer-1", "列表平均值为 -3，每个值加 2 后，新平均值是多少？", -1),
    "total_with_fee": ("fee-transfer-1", "金额为 [1, 2, 3, 4]，另加一次固定费用 5。总金额是多少？", 15),
    "pair_count": ("pair-transfer-1", "物品列表为 [0, 0, -9, 2, 2]，每件需两张标签。共需多少张？", 10),
    "average_with_zero": ("zero-transfer-1", "列表总和为 12，共 3 个元素。追加一个 0 后，平均值是多少？", 3),
}


def challenge(exercise_id):
    if not isinstance(exercise_id, str) or exercise_id not in EXERCISES:
        raise ValueError("Unknown exercise_id.")
    question_id, question, _ = _QUESTIONS[exercise_id]
    return {"exercise_id": exercise_id, "question_id": question_id,
            "question": question, "answer_type": "number"}


def verify(exercise_id, code, answer, explanation=""):
    challenge(exercise_id)
    if not isinstance(code, str):
        raise ValueError("code must be a string.")
    if type(answer) not in (int, float):
        raise ValueError("answer must be a finite number.")
    try:
        finite = math.isfinite(answer)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("answer must be a finite number.")
    if not isinstance(explanation, str) or len(explanation) > 500:
        raise ValueError("explanation must be a string of at most 500 characters.")
    if check_submission(code, exercise_id)["status"] != "passed":
        raise LearningConflict("Pass the original exercise before checking transfer.")
    expected = _QUESTIONS[exercise_id][2]
    correct = math.isclose(answer, expected, rel_tol=1e-9, abs_tol=1e-9)
    return {
        "correct": correct,
        "original_passed": True,
        "transfer_checked": True,
        "explanation_recorded": bool(explanation.strip()),
        "message": ("原题已通过；本次迁移题答案正确。解释仅作自述记录，未评分。"
                    if correct else "原题已通过；本次迁移题答案还需核对。解释仅作自述记录，未评分。"),
    }
