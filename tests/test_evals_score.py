"""Checks for the review scorer, the tool that turns hand-graded rubric fields into reportable numbers.

The scorer is what makes the 72/72 claims in evals/README.md reproducible, so these tests pin down
that it counts the way the written rubric says, ignores positions that were never supposed to be
graded, and refuses to let a report contradict the rules the product itself enforces.
"""

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

import agentarts
from evals import score


def graded(evidence_ok=True, actionable=True, answer_leaked=False):
    return {"evidence_ok": evidence_ok, "actionable": actionable, "answer_leaked": answer_leaked}


def make_report(local_review=None, endpoint=None, note="测试采集", summary=None, hint="检查分母用的是哪个量。"):
    """One sample at one level, in the shape evals.run writes."""
    row = {"level": 1, "local": {"source": "local", "hint": hint, "case_id": "C01",
                                 "elapsed_ms": 0.1, "review": local_review}}
    if endpoint is not None:
        row["endpoint"] = endpoint
    report = {
        "mode": "endpoint-comparison" if endpoint else "local-only",
        "note": note,
        "summary": summary if summary is not None else {"samples": 1, "local_rows": 1},
        "records": [{"sample_id": "N01", "category": "分母", "focus": "除法",
                     "diagnosis": {"kind": "zero_division", "line": 3},
                     "failed_cases": [{"id": "C01", "input": [7], "status": "error"}],
                     "levels": [row]}],
    }
    return report


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def write(self, report, name="report.json"):
        path = Path(self.dir.name) / name
        path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        return path

    def run_main(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = score.main(argv)
        return code, out.getvalue()

    def test_partial_reviews_are_not_counted_as_reviewed(self):
        counts = score.tally([{"review": graded()}, {"review": {"evidence_ok": True, "actionable": None,
                                                               "answer_leaked": False}}, {"hint": "无复核"}])
        self.assertEqual(counts["rows"], 3)
        self.assertEqual(counts["reviewed"], 1, "三项都打分了才算复核过")
        self.assertEqual(counts["evidence_ok"], 2)
        self.assertEqual(counts["evidence_ok_scored"], 2)
        self.assertEqual(counts["actionable_scored"], 1, "分母只算该项打了分的提示")

    def test_fallback_hint_must_equal_the_local_one(self):
        endpoint = {"outcome": "fallback", "source": "local", "hint": "另一套说法", "case_id": "C01",
                    "elapsed_ms": 12.0}
        result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
        self.assertEqual(result["issues"], ["N01 第 1 级：回退提示与同级本地提示不一致"])
        self.assertEqual(result["pending"], [], "回退位置重复本地文本，不该再排进复核清单")

    def test_error_rows_are_counted_without_a_hint(self):
        endpoint = {"outcome": "error", "error_kind": "TimeoutError", "elapsed_ms": 8000.0}
        result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["outcomes"]["error"], 1)
        self.assertEqual(result["pending"], [])

    def test_cloud_rows_missing_request_id_are_flagged(self):
        endpoint = {"outcome": "cloud", "source": "agentarts", "hint": "手算总和与元素个数。", "case_id": "C01",
                    "elapsed_ms": 900.0, "review": graded()}
        result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
        self.assertIn("request_id", result["issues"][0])

    def test_cloud_hints_that_break_the_client_rules_are_flagged(self):
        for hint, expected in (("a" * 241, "240"), ("第一行\n第二行", "240"),
                               ("把 return 改成 sum(nums) / len(nums) 就对了。", "可复制答案")):
            endpoint = {"outcome": "cloud", "source": "agentarts", "hint": hint, "case_id": "C01",
                        "request_id": "r-1", "elapsed_ms": 900.0, "review": graded()}
            result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
            self.assertTrue(any(expected in issue for issue in result["issues"]), f"{hint[:20]} 未被标记：{result['issues']}")

    def test_human_leak_verdict_without_machine_support_asks_to_widen_the_rule(self):
        endpoint = {"outcome": "cloud", "source": "agentarts", "hint": "直接写总和除以个数即可。", "case_id": "C01",
                    "request_id": "r-1", "elapsed_ms": 900.0, "review": graded(answer_leaked=True)}
        result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
        self.assertTrue(any("_SOLUTION" in issue for issue in result["issues"]))

    def test_case_id_outside_the_failed_cases_is_flagged(self):
        endpoint = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C09",
                    "request_id": "r-1", "elapsed_ms": 900.0, "review": graded()}
        result = score.score_report(self.write(make_report(local_review=graded(), endpoint=endpoint)))
        self.assertTrue(any("case_id" in issue for issue in result["issues"]))

    def test_summary_claims_are_recounted_from_the_rows(self):
        summary = {"samples": 1, "local_rows": 9, "cloud_rows": 0,
                   "local_review": {"evidence_ok": 0, "actionable": 0, "answer_leaked": 0}}
        result = score.score_report(self.write(make_report(local_review=graded(), summary=summary)))
        text = " ".join(result["issues"])
        self.assertIn("summary.local_rows=9", text)
        self.assertIn("summary.local_review.evidence_ok=0", text)

    def test_median_timing_is_verified(self):
        summary = {"samples": 1, "local_rows": 1, "local_median_ms": 99.0}
        result = score.score_report(self.write(make_report(local_review=graded(), summary=summary)))
        self.assertTrue(any("local_median_ms" in issue for issue in result["issues"]))

    def test_pending_positions_cover_both_sides_of_a_pair(self):
        endpoint = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                    "request_id": "r-1", "elapsed_ms": 900.0, "review": {}}
        result = score.score_report(self.write(make_report(endpoint=endpoint)))
        self.assertEqual([entry[2] for entry in result["pending"]], ["local", "endpoint"])
        self.assertEqual(result["issues"], [], "未打分不是错误，只进复核清单")

    def test_paired_scores_are_only_taken_over_cloud_hits(self):
        cloud = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                 "request_id": "r-1", "elapsed_ms": 900.0, "review": graded(actionable=False)}
        fallback = {"outcome": "fallback", "source": "local", "hint": "检查分母用的是哪个量。", "case_id": "C01",
                    "elapsed_ms": 12.0}
        report = make_report(local_review=graded(), endpoint=cloud)
        report["records"][0]["levels"].append({"level": 2, "local": dict(report["records"][0]["levels"][0]["local"]),
                                               "endpoint": fallback})
        report["summary"] = {"samples": 1, "local_rows": 2, "cloud_rows": 1, "fallback_rows": 1}
        result = score.score_report(self.write(report))
        self.assertEqual(result["paired"]["cloud_pairs"], 1)
        self.assertEqual(result["paired"]["cloud"]["actionable"], 0)
        self.assertEqual(result["endpoint"]["actionable_scored"], 1)

    def test_local_text_drift_is_detected(self):
        reference = make_report(local_review=graded())
        other = json.loads(json.dumps(reference))
        other["records"][0]["levels"][0]["local"]["hint"] = "改过的本地提示"
        drift = score.compare_local(reference, other)
        self.assertEqual([entry[0] for entry in drift], [("N01", 1)])
        self.assertEqual(drift[0][1], "检查分母用的是哪个量。")
        self.assertEqual(drift[0][2], "改过的本地提示")

    def test_drift_reports_a_position_that_only_exists_on_one_side(self):
        reference = make_report(local_review=graded())
        other = json.loads(json.dumps(reference))
        other["records"][0]["levels"].append({"level": 2, "local": {"hint": "多出的一级", "case_id": "C01",
                                                                    "elapsed_ms": 0.1}})
        drift = score.compare_local(reference, other)
        self.assertEqual([entry[0] for entry in drift], [("N01", 2)])
        self.assertEqual(drift[0][1], "（缺该位置）")

    def test_bad_structure_is_reported_not_raised(self):
        path = self.write({"mode": "local-only", "summary": {}, "records": []})
        with self.assertRaises(ValueError):
            score.score_report(path)

    def test_cli_exit_codes_and_read_only_behaviour(self):
        endpoint = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                    "request_id": "r-1", "elapsed_ms": 900.0, "review": graded()}
        good = self.write(make_report(local_review=graded(), endpoint=endpoint), "good.json")
        broken = self.write(make_report(endpoint=endpoint), "broken.json")
        before = good.read_text(encoding="utf-8")
        code, text = self.run_main([str(good), "--require-complete"])
        self.assertEqual(code, 0)
        self.assertIn("有效配对 1 对", text)
        self.assertEqual(good.read_text(encoding="utf-8"), before, "打分工具不该改写采集文件")
        self.assertEqual(self.run_main([str(broken)])[0], 0)
        code, text = self.run_main([str(broken), "--require-complete"])
        self.assertEqual(code, 1)
        self.assertIn("尚未复核", text)
        self.assertEqual(self.run_main([str(Path(self.dir.name) / "missing.json")])[0], 2)

    def test_cli_can_compare_two_reports_against_a_baseline(self):
        cloud = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                 "request_id": "r-1", "elapsed_ms": 900.0, "review": graded()}
        good = self.write(make_report(local_review=graded(), endpoint=cloud), "paired.json")
        self.assertEqual(self.run_main([str(self.write(make_report(local_review=graded()), "same.json")),
                                        "--against", str(good)])[0], 0, "本地文本一致时不该报漂移")
        stale = make_report(local_review=graded())
        stale["records"][0]["levels"][0]["local"]["hint"] = "改过的本地提示"
        code, text = self.run_main([str(self.write(stale, "stale.json")), "--against", str(good)])
        self.assertEqual(code, 1, "本地文本漂移说明两侧不再可比")
        self.assertIn("本地侧漂移 1 处", text)
        self.assertIn("N01 第 1 级", text)

    def test_scorer_mirrors_the_client_rules(self):
        self.assertEqual(score.MAX_HINT_LENGTH, agentarts._MAX_HINT_LENGTH, "两处上限必须一起改")
        self.assertFalse(agentarts._SOLUTION.search("检查分母用的是哪个量。"), "干净提示不该被判为泄露")
        self.assertRegex("把 return 改成 sum(nums) / len(nums) 就对了。", agentarts._SOLUTION)

    def test_graded_baseline_shortens_the_review_worklist(self):
        cloud = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                 "request_id": "r-1", "elapsed_ms": 900.0, "review": {}}
        paired = self.write(make_report(local_review=None, endpoint=cloud), "paired.json")
        baseline = self.write(make_report(local_review=graded()), "baseline.json")
        code, text = self.run_main([str(paired), "--against", str(baseline)])
        self.assertEqual(code, 0)
        self.assertIn("可沿用基准报告已打的 1 条打分", text)

    def test_ungraded_baseline_does_not_claim_a_shortcut(self):
        cloud = {"outcome": "cloud", "source": "agentarts", "hint": "核对分母。", "case_id": "C01",
                 "request_id": "r-1", "elapsed_ms": 900.0, "review": {}}
        left = self.write(make_report(local_review=None, endpoint=cloud), "a.json")
        right = self.write(make_report(local_review=None, endpoint=cloud), "b.json")
        code, text = self.run_main([str(left), "--against", str(right)])
        self.assertEqual(code, 0)
        self.assertNotIn("可沿用", text)

    def test_shipped_baseline_still_supports_the_published_numbers(self):
        reports = Path(score.__file__).with_name("local-baseline.json")
        result = score.score_report(reports)
        self.assertEqual(result["issues"], [], f"本地基线报告应自洽：{result['issues']}")
        self.assertEqual(result["local"]["rows"], 72, "三道题各 12、6、6 条样本，每条三级")
        self.assertEqual(result["local"]["reviewed"], 72)
        self.assertEqual(result["local"]["evidence_ok"], 72)
        self.assertEqual(result["local"]["actionable"], 72)
        self.assertEqual(result["local"]["answer_leaked"], 0)
        self.assertEqual(result["pending"], [])

    def test_shipped_mock_report_is_wiring_only(self):
        report = score.score_report(Path(score.__file__).parent / "history" / "teammate" / "mock-paired-results.json")
        self.assertEqual(report["issues"], [], f"模拟配对报告应自洽：{report['issues']}")
        self.assertEqual(report["outcomes"], {"cloud": 72, "fallback": 0, "error": 0})
        self.assertEqual(len(report["pending"]), 144, "模拟提示不参与质量比较，两侧都算待复核")
        self.assertIn("模拟", report["note"])


if __name__ == "__main__":
    unittest.main()
