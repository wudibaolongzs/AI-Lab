import json
import tempfile
import unittest
from pathlib import Path

from tools.compare_paired import compare, main


def report(rows):
    records = {}
    for sample, level, evidence, actionable in rows:
        record = records.setdefault(sample, {"sample_id": sample, "levels": []})
        record["levels"].append({
            "level": level,
            "endpoint": {"outcome": "cloud", "review": {
                "evidence_ok": evidence, "actionable": actionable, "answer_leaked": False}},
        })
    return {"records": list(records.values())}


def leaked_report(sample, leaked):
    return {"records": [{"sample_id": sample, "levels": [{
        "level": 1,
        "endpoint": {"outcome": "cloud", "review": {
            "evidence_ok": True, "actionable": True, "answer_leaked": leaked}}}]}]}


class ComparePairedTests(unittest.TestCase):
    def test_answer_leaked_false_is_not_a_failure(self):
        same = compare(leaked_report("N01", False), leaked_report("N01", False))
        self.assertEqual(same["summary"]["answer_leaked"]["passed"], 1)
        self.assertEqual(same["summary"]["answer_leaked"]["still_failed"], 0)
        fixed = compare(leaked_report("N01", True), leaked_report("N01", False))
        self.assertEqual(fixed["summary"]["answer_leaked"]["fixed"], 1)
        regressed = compare(leaked_report("N01", False), leaked_report("N01", True))
        self.assertEqual(regressed["summary"]["answer_leaked"]["regressed"], 1)

    def test_fixed_regressed_and_still_failed_are_separated(self):
        before = report([("N01", 1, False, False), ("N02", 1, True, True),
                         ("N03", 1, False, True)])
        after = report([("N01", 1, True, True), ("N02", 1, False, True),
                        ("N03", 1, False, True)])
        result = compare(before, after)
        self.assertEqual(result["compared_positions"], 3)
        self.assertEqual(result["summary"]["evidence_ok"]["fixed"], 1)
        self.assertEqual(result["summary"]["evidence_ok"]["regressed"], 1)
        self.assertEqual(result["summary"]["evidence_ok"]["still_failed"], 1)
        self.assertEqual(result["summary"]["actionable"]["fixed"], 1)

    def test_unreviewed_positions_are_counted(self):
        before = report([("N01", 1, False, False)])
        after = report([("N01", 1, None, None)])
        result = compare(before, after)
        self.assertEqual(result["summary"]["evidence_ok"]["unreviewed"], 1)

    def test_exit_code_flags_regressions(self):
        with tempfile.TemporaryDirectory() as directory:
            before = Path(directory) / "before.json"
            after = Path(directory) / "after.json"
            before.write_text(json.dumps(report([("N01", 1, False, False)])), encoding="utf-8")
            after.write_text(json.dumps(report([("N01", 1, True, True)])), encoding="utf-8")
            self.assertEqual(main([str(before), str(after)]), 0)
            after.write_text(json.dumps(report([("N01", 1, False, True)])), encoding="utf-8")
            self.assertEqual(main([str(before), str(after)]), 0)
            before.write_text(json.dumps(report([("N01", 1, True, True)])), encoding="utf-8")
            self.assertEqual(main([str(before), str(after)]), 1)


if __name__ == "__main__":
    unittest.main()