"""Fixed numeric transfer checks, separate from original code acceptance.

No student source is executed by Python or sent to a remote service. Explanations
are optional self-reports; they are never scored as evidence of understanding.
"""
import math
import question_bank

from exercise import EXERCISES, check_submission


class LearningConflict(ValueError):
    """Original exercise has not passed; HTTP adapters should return 409."""




def challenge(exercise_id):
    if not isinstance(exercise_id, str) or exercise_id not in EXERCISES:
        raise ValueError("Unknown exercise_id.")
    transfer = question_bank.get_problem(exercise_id).get("transfer")
    if not transfer:
        return {"exercise_id": exercise_id, "available": False, "question": "暂未配置理解验证"}
    question_id, question = transfer["question_id"], transfer["question"]
    return {"exercise_id": exercise_id, "question_id": question_id,
            "question": question, "answer_type": "number"}


def verify(exercise_id, code, answer, explanation=""):
    challenge(exercise_id)
    if not question_bank.get_problem(exercise_id).get("transfer"):
        raise LearningConflict("暂未配置理解验证")
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
    expected = question_bank.get_problem(exercise_id)["transfer"]["answer"]
    correct = math.isclose(answer, expected, rel_tol=1e-9, abs_tol=1e-9)
    return {
        "correct": correct,
        "original_passed": True,
        "transfer_checked": True,
        "explanation_recorded": bool(explanation.strip()),
        "message": ("原题已通过；本次迁移题答案正确。解释仅作自述记录，未评分。"
                    if correct else "原题已通过；本次迁移题答案还需核对。解释仅作自述记录，未评分。"),
    }
