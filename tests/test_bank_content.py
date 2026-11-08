import json
from pathlib import Path
import unittest

from bank_engine import check

ROOT = Path(__file__).resolve().parents[1]


class BankContentTests(unittest.TestCase):
    def setUp(self):
        self.pack = json.loads((ROOT / 'data/exercism-foundations.json').read_text(encoding='utf-8'))

    def test_twenty_stable_licensed_problems(self):
        problems = self.pack['problems']
        self.assertEqual(len(problems), 20)
        self.assertEqual(len({p['id'] for p in problems}), 20)
        groups = {}
        revision = (ROOT / 'third_party/exercism/REVISION').read_text().strip()
        for problem in problems:
            self.assertTrue(problem['id'].startswith('ex_'))
            self.assertEqual(problem['source']['revision'], revision)
            self.assertEqual(problem['source']['license'], 'MIT')
            slug = problem['source']['url'].split('/')[-1]
            groups[slug] = groups.get(slug, 0) + 1
            self.assertGreaterEqual(len(problem['cases']), 4)
            self.assertEqual(len(problem['hints']), 3)
        self.assertEqual(sorted(groups.values()), [1,1,1,1,1,3,3,4,5])

    def test_references_pass_and_starters_fail_in_bounded_engine(self):
        for problem in self.pack['problems']:
            with self.subTest(problem=problem['id']):
                good = check(problem['reference_code'], problem)
                self.assertEqual(good['status'], 'passed', good)
                bad = check(problem['starter_code'], problem)
                self.assertEqual(bad['status'], 'failed', bad)
                self.assertEqual(bad['diagnosis']['kind'], 'wrong_result')

    def test_eval_samples_record_first_failure(self):
        problems = {p['id']: p for p in self.pack['problems']}
        samples = json.loads((ROOT / 'evals/bank-samples.json').read_text(encoding='utf-8'))
        self.assertEqual(len(samples), 20)
        for sample in samples:
            result = check(sample['code'], problems[sample['exercise']])
            first = next(c for c in result['cases'] if c['status'] != 'passed')
            self.assertEqual(first['id'], sample['case_id'])
            self.assertEqual(result['diagnosis']['kind'], sample['diagnosis_kind'])


if __name__ == '__main__':
    unittest.main()
