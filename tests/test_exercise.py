import unittest


class AverageExerciseTests(unittest.TestCase):
    def test_constant_result_hint_asks_to_compare_inputs(self):
        from exercise import check_submission

        result = check_submission("def average(nums):\n    return 25")
        self.assertIn("返回值相同", result["hints"][1])
        self.assertIn("输入", result["hints"][1])

    def test_numeric_range_hint_gives_a_concrete_check(self):
        from exercise import check_submission

        result = check_submission("def average(nums):\n    return sum(nums) * 1000000000000")
        self.assertIn("最小值和最大值", result["hints"][0])

    def test_starter_produces_execution_evidence_and_three_hints(self):
        from exercise import EXERCISE, check_submission

        result = check_submission(EXERCISE["starter_code"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(result["hints"]), 3)
        self.assertEqual(result["cases"][0]["input"], [10, 20, 30, 40])
        self.assertEqual(result["cases"][0]["expected"], 25.0)
        self.assertAlmostEqual(result["cases"][0]["actual"], 100 / 3)
        self.assertTrue(any(case["status"] == "error" for case in result["cases"]))

    def test_corrected_submission_passes_every_case(self):
        from exercise import EXERCISE, check_submission

        result = check_submission(EXERCISE["starter_code"].replace("(len(nums) - 1)", "len(nums)"))
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["passed"], result["total"])
        self.assertEqual(result["hints"], [])
        self.assertIsNone(result["diagnosis"])

    def test_hard_coded_sample_answer_fails_other_inputs(self):
        from exercise import check_submission

        result = check_submission("def average(nums):\n    return 25")
        self.assertEqual(result["passed"], 1)
        self.assertEqual(result["status"], "failed")

    def test_unsupported_syntax_is_rejected_before_running_any_case(self):
        from exercise import check_submission

        submissions = (
            "def average(nums):\n    ignored = open('file')\n    return 25",
            "def average(nums):\n    return 1 / 0\n    ignored = nums.__class__",
            "def average(nums: str):\n    return sum(nums) / len(nums)",
            "def average(nums):\n    sum = 1\n    return sum(nums)",
            "def average(nums):\n    __debug__ = 1\n    return 25",
        )
        for code in submissions:
            with self.subTest(code=code):
                result = check_submission(code)
                self.assertEqual(result["status"], "invalid")
                self.assertEqual(result["diagnosis"]["kind"], "unsupported")
                self.assertEqual(result["cases"], [])

    def test_reports_syntax_and_runtime_errors_separately(self):
        from exercise import check_submission

        invalid = check_submission("def average(nums)\n    return 25")
        self.assertEqual(invalid["diagnosis"]["kind"], "syntax")
        self.assertEqual(invalid["diagnosis"]["line"], 1)
        self.assertEqual(check_submission("\ud800")["diagnosis"]["kind"], "syntax")
        failed = check_submission("def average(nums):\n    denominator = len(nums) - len(nums)\n    return 25 / denominator")
        self.assertEqual(failed["diagnosis"]["kind"], "zero_division")
        self.assertEqual(failed["diagnosis"]["line"], 3)
        self.assertIsNone(failed["cases"][0]["actual"])

    def test_numeric_bounds_cover_literals_and_intermediate_results(self):
        from exercise import check_submission

        invalid = check_submission("def average(nums):\n    return 1e999")
        self.assertEqual(invalid["status"], "invalid")
        result = check_submission("def average(nums):\n    return 1000000000 * 1000000000")
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["diagnosis"]["kind"], "numeric_range")


class ListExerciseTests(unittest.TestCase):
    def test_empty_lists_and_negative_values_use_selected_exercise(self):
        from exercise import check_submission

        submissions = (
            ("sum", "def list_sum(nums):\n    return sum(nums)", -3),
            ("count", "def list_count(nums):\n    return len(nums)", 3),
        )
        for exercise_id, code, expected in submissions:
            with self.subTest(exercise_id=exercise_id):
                result = check_submission(code, exercise_id)
                self.assertEqual(result["status"], "passed")
                cases = {tuple(case["input"]): case for case in result["cases"]}
                self.assertEqual(cases[()]["actual"], 0)
                self.assertEqual(cases[(-5, 2, 0)]["expected"], expected)
                self.assertEqual(cases[(-5, 2, 0)]["actual"], expected)

    def test_failed_starters_show_topic_specific_hints(self):
        from exercise import EXERCISES, check_submission

        for exercise_id, topic in (("sum", "总和"), ("count", "元素个数")):
            with self.subTest(exercise_id=exercise_id):
                result = check_submission(EXERCISES[exercise_id]["starter_code"], exercise_id)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(len(result["hints"]), 3)
                self.assertIn(topic, result["hints"][2])

    # One submission per exercise that trips each diagnosis the grader can report.
    TRIGGERS = {
        "sum": {
            "wrong_result": "return len(nums)",
            "zero_division": "return sum(nums) / len(nums) * len(nums)",
            "numeric_range": "return sum(nums) * 500000000000",
        },
        "count": {
            "wrong_result": "return sum(nums)",
            "zero_division": "return len(nums) / len(nums) * len(nums)",
            "numeric_range": "return len(nums) * 500000000000",
        },
    }
    SIGNATURES = {"sum": "list_sum", "count": "list_count"}

    def hints_for(self, exercise_id, body):
        from exercise import check_submission

        code = f"def {self.SIGNATURES[exercise_id]}(nums):\n    {body}\n"
        result = check_submission(code, exercise_id)
        self.assertEqual(result["status"], "failed", code)
        return result["diagnosis"]["kind"], result["hints"]

    def test_sum_and_count_hints_change_with_the_diagnosis(self):
        """Hints 1 and 3 used to be frozen per exercise, so a division bug still read as a wrong total."""
        for exercise_id, per_kind in self.TRIGGERS.items():
            seen = {}
            for kind, body in per_kind.items():
                with self.subTest(exercise_id=exercise_id, kind=kind):
                    got, hints = self.hints_for(exercise_id, body)
                    self.assertEqual(got, kind)
                    self.assertEqual(len(hints), 3)
                    for hint in hints:
                        self.assertEqual(len(hint.splitlines()), 1, hint)
                        self.assertTrue(0 < len(hint) <= 240, hint)
                    seen[kind] = hints
            self.assertNotEqual(seen["wrong_result"][0], seen["zero_division"][0], "第 1 句没跟着诊断变")
            self.assertNotEqual(seen["wrong_result"][2], seen["zero_division"][2], "第 3 句没跟着诊断变")
            self.assertNotEqual(seen["wrong_result"][0], seen["numeric_range"][0], "第 1 句没跟着诊断变")
            self.assertIn("除法", seen["zero_division"][0], "除零诊断的第一句应当点出除法")

    def test_sum_and_count_hints_do_not_borrow_the_average_exercise(self):
        """Comparing a total against an element count is average advice; these tasks need one quantity."""
        forbidden = {"sum": ("平均值", "分子", "分母"), "count": ("平均值", "分子", "分母", "总和")}
        for exercise_id, per_kind in self.TRIGGERS.items():
            for kind, body in per_kind.items():
                _, hints = self.hints_for(exercise_id, body)
                for word in forbidden[exercise_id]:
                    with self.subTest(exercise_id=exercise_id, kind=kind, word=word):
                        self.assertNotIn(word, " ".join(hints))

    def test_overflow_hints_do_not_point_at_a_value_the_page_hides(self):
        """An out-of-range case renders 实际 as —, so level 3 must name the student's own expression."""
        from exercise import check_submission

        for exercise_id in ("sum", "count"):
            body = self.TRIGGERS[exercise_id]["numeric_range"]
            code = f"def {self.SIGNATURES[exercise_id]}(nums):\n    {body}\n"
            result = check_submission(code, exercise_id)
            failed = [case for case in result["cases"] if case["status"] != "passed"][0]
            with self.subTest(exercise_id=exercise_id):
                self.assertIsNone(failed.get("actual"), "超限用例没有可显示的实际值")
                self.assertIn("你的式子算出的结果", result["hints"][2])
                self.assertNotIn("看返回值比它", result["hints"][2])

    def test_average_hints_keep_the_graded_wording(self):
        """evals/local-baseline.json scored these average strings in 36 positions; rewording voids that review."""
        from exercise import HINT_GUIDANCE, HINT_LOCATION

        self.assertEqual(HINT_GUIDANCE["average"], {
            "zero_division": ("先数一数这个列表的元素个数，再想想它与除数的关系。",
                              "把总和和实际元素个数分开核对，再用这个失败用例复测。"),
            "numeric_range": ("圈出输入中的最小值和最大值，再判断平均值是否应落在两者之间。",
                              "分别手算列表总和与元素个数，用这两个量检查各步运算。"),
            "wrong_result": ("试着手算这个列表的总和，再数一数元素个数。",
                             "把分子和分母分别写在纸上，确认分子等于列表总和、分母等于实际元素个数。"),
        })
        self.assertEqual(HINT_LOCATION["wrong_result"], "从第 {line} 行的返回表达式开始，回查参与计算的变量。")
        self.assertTrue({"average", "sum", "count"}.issubset(HINT_GUIDANCE))
        self.assertEqual(set(HINT_GUIDANCE["sum"]), set(HINT_LOCATION), "每题都要覆盖全部诊断类别")

    def test_list_exercise_rejects_file_access(self):
        from exercise import check_submission

        result = check_submission("def list_sum(nums):\n    return open('data.txt')", "sum")
        self.assertEqual(result["status"], "invalid")
        self.assertEqual(result["diagnosis"]["kind"], "unsupported")
        self.assertEqual(result["cases"], [])
