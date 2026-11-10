"""Offline checks that the mock runtime really speaks what agentarts.py expects to hear.

These cover the contract, not hint quality: the event shape the client parses, the input
validation mirroring the workflow start node, and the scripted hint text staying inside the
rules the client enforces. The end-to-end side lives in ``tools/verify_agentarts.py``.
"""

import io
import json
from pathlib import Path
import time
import unittest

from agentarts import WorkflowFailure, _SOLUTION, _workflow_result
from exercise import EXERCISES, check_submission
from tools.mock_agentarts import ANSWER_LEAK, _validate, build_events, build_hint

SAMPLES = json.loads((Path(__file__).resolve().parent.parent / "evals" / "samples.json")
                     .read_text(encoding="utf-8"))


def sse(events):
    return io.BytesIO("".join(f"data: {json.dumps(event, ensure_ascii=False)}\r\n\r\n"
                              for event in events).encode("utf-8"))


def parse(events):
    return _workflow_result(sse(events), time.monotonic() + 5)


class MockRuntimeContractTests(unittest.TestCase):
    def setUp(self):
        self.result = check_submission(EXERCISES["average"]["starter_code"], "average")
        self.failed = [case for case in self.result["cases"] if case["status"] != "passed"]
        self.summary = "计算列表平均值：用例 C01 期望 25.0，实际 33.33。"
        self.hint = "用例 C01 的输入是 [10, 20, 30, 40]，期望 25.0，实际 33.33。平均值是拿哪两个量相除得到的？"

    def test_published_event_shape_is_what_the_client_reads(self):
        fields, execution_id = parse(build_events("ok", "mock-exec-0001", "C01", self.summary, self.hint))
        self.assertEqual(execution_id, "mock-exec-0001")
        self.assertEqual(fields, {"hint": self.hint, "case_id": "C01"})

    def test_abnormal_runs_yield_no_cloud_hint(self):
        for mode in ("waiting", "error-event"):
            with self.subTest(mode=mode):
                events = build_events(mode, "mock-exec-0002", "C01", self.summary, self.hint)
                if mode == "error-event":
                    with self.assertRaises(WorkflowFailure):
                        parse(events)
                else:
                    self.assertEqual(parse(events), (None, None))

    def test_answer_leaking_run_is_still_rejected_by_the_client(self):
        events = build_events("leak-answer", "mock-exec-0003", "C01", self.summary, self.hint)
        fields, _ = parse(events)
        self.assertEqual(fields["hint"], ANSWER_LEAK)
        self.assertRegex(fields["hint"], _SOLUTION)

    def test_scripted_hints_respect_the_rules_the_client_enforces(self):
        for sample in SAMPLES:
            result = check_submission(sample["code"], sample["exercise"])
            failed = [case for case in result["cases"] if case["status"] != "passed"]
            for level in (1, 2, 3):
                with self.subTest(sample=sample["id"], level=level):
                    hint = build_hint(level, failed[0], result["diagnosis"], sample["exercise"])
                    self.assertEqual(len(hint.splitlines()), 1)
                    self.assertTrue(0 < len(hint) <= 240, hint)
                    self.assertNotRegex(hint, _SOLUTION)
                    self.assertNotEqual(hint, result["hints"][level - 1])

    def test_scripted_hints_follow_the_exercise_and_the_diagnosis(self):
        """The sum and count branches used to sit behind the average-flavoured diagnosis branches."""
        triggers = {
            "sum": ("def list_sum(nums):\n    return len(nums)\n",
                    "def list_sum(nums):\n    return sum(nums) / len(nums) * len(nums)\n",
                    "def list_sum(nums):\n    return sum(nums) * 500000000000\n"),
            "count": ("def list_count(nums):\n    return sum(nums)\n",
                      "def list_count(nums):\n    return len(nums) / len(nums) * len(nums)\n",
                      "def list_count(nums):\n    return len(nums) * 500000000000\n"),
        }
        for exercise_id, codes in triggers.items():
            triples = []
            for code in codes:
                result = check_submission(code, exercise_id)
                failed = [case for case in result["cases"] if case["status"] != "passed"]
                with self.subTest(exercise_id=exercise_id, code=code):
                    texts = [build_hint(level, failed[0], result["diagnosis"], exercise_id)
                             for level in (1, 2, 3)]
                    self.assertEqual(len(set(texts)), 3, texts)
                    for hint in texts:
                        self.assertTrue(0 < len(hint) <= 240, hint)
                    joined = " ".join(texts)
                    self.assertNotIn("None", joined, "报错用例没有实际值，不能把 None 印进提示")
                    for word in ("平均值", "分子", "分母"):
                        self.assertNotIn(word, joined, f"{exercise_id} 题的提示借用了平均值题的说法")
                    triples.append(texts)
            self.assertNotEqual(triples[0][0], triples[1][0], "第 1 级没跟着诊断变")
            self.assertNotEqual(triples[0][2], triples[2][2], "第 3 级没跟着诊断变")

    def test_overflow_scripted_hint_names_the_students_expression(self):
        """The page shows 实际 as — for an out-of-range case; the hint must not quote a hidden value."""
        result = check_submission("def list_sum(nums):\n    return sum(nums) * 500000000000\n", "sum")
        failed = [case for case in result["cases"] if case["status"] != "passed"][0]
        hint = build_hint(3, failed, result["diagnosis"], "sum")
        self.assertIn("你的式子算出的结果", hint)
        self.assertNotIn("看返回值比它", hint)

    def test_first_failed_case_id_is_the_one_the_client_accepts(self):
        for sample in SAMPLES:
            result = check_submission(sample["code"], sample["exercise"])
            failed = [case for case in result["cases"] if case["status"] != "passed"]
            build_hint(1, failed[0], result["diagnosis"], sample["exercise"])
            with self.subTest(sample=sample["id"]):
                self.assertEqual(failed[0]["id"], sample["case_id"])

    def test_validate_mirrors_the_start_node_contract(self):
        evidence = json.dumps({"cases": self.failed, "diagnosis": self.result["diagnosis"]}, ensure_ascii=False)
        payload = {"inputs": {"exercise_title": "计算列表平均值", "evidence_json": evidence, "hint_level": 2}}
        title, level, case, diagnosis, exercise = _validate(payload)
        self.assertEqual((title, level), ("计算列表平均值", 2))
        self.assertEqual(case["id"], "C01")
        self.assertEqual(diagnosis, self.result["diagnosis"])
        self.assertEqual(exercise, "average")

    def test_exercise_id_selects_the_wording_family(self):
        evidence = json.dumps({"cases": self.failed, "diagnosis": self.result["diagnosis"]}, ensure_ascii=False)
        base = {"exercise_title": "计算列表元素个数", "evidence_json": evidence, "hint_level": 1}
        cases = (({**base, "exercise_id": "sum"}, "sum"), (base, "count"),
                 ({**base, "exercise_title": "计算列表平均值"}, "average"),
                 ({**base, "exercise_title": "自定义题目"}, "generic"))
        for payload, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(_validate({"inputs": payload})[4], expected)

    def test_validate_rejects_inputs_a_published_workflow_would_refuse(self):
        evidence = json.dumps({"cases": self.failed, "diagnosis": self.result["diagnosis"]})
        base = {"exercise_title": "计算列表平均值", "evidence_json": evidence, "hint_level": 2}
        broken = [
            {}, {"inputs": []}, {"inputs": [base]},
            {"inputs": {**base, "hint_level": "2"}}, {"inputs": {**base, "hint_level": 0}},
            {"inputs": {**base, "hint_level": 4}}, {"inputs": {**base, "hint_level": True}},
            {"inputs": {**base, "exercise_title": "  "}}, {"inputs": {**base, "exercise_title": 3}},
            {"inputs": {**base, "exercise_id": 3}}, {"inputs": {**base, "exercise_id": ["sum"]}},
            {"inputs": {**base, "evidence_json": {"cases": self.failed}}},
            {"inputs": {**base, "evidence_json": "not json"}},
            {"inputs": {**base, "evidence_json": json.dumps({"cases": [], "diagnosis": {}})}},
            {"inputs": {**base, "evidence_json": json.dumps({"cases": self.failed})}},
            {"inputs": {**base, "evidence_json": json.dumps({"cases": [{"expected": 1}, ],
                                                            "diagnosis": {}})}},
            {"inputs": {**base, "evidence_json": json.dumps({"cases": self.failed,
                                                             "diagnosis": "wrong"})}},
        ]
        for payload in broken:
            with self.subTest(payload=str(payload)[:70]):
                with self.assertRaises(ValueError):
                    _validate(payload)


if __name__ == "__main__":
    unittest.main()
