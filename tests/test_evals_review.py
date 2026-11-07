import csv
import tempfile
import unittest
from pathlib import Path
from evals import review
from tests.test_evals_score import make_report, graded


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'review.csv'
        self.report = make_report()
        review.export_csv(self.report, self.path)

    def rewrite(self, transform):
        with self.path.open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.DictReader(stream))
        rows = transform(rows)
        with self.path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=review.COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def test_blank_roundtrip_stays_pending_and_preserves_raw(self):
        result = review.import_csv(self.report, self.path)
        self.assertEqual(result['records'][0]['levels'][0]['local']['review'],
                         dict.fromkeys(review.FIELDS))
        self.assertIsNone(self.report['records'][0]['levels'][0]['local']['review'])

    def test_explicit_verdicts(self):
        self.rewrite(lambda rows: [dict(rows[0], evidence_ok='true', actionable='false')])
        result = review.import_csv(self.report, self.path)
        self.assertEqual(result['records'][0]['levels'][0]['local']['review'],
                         dict(evidence_ok=True, actionable=False, answer_leaked=None))

    def test_formula_and_apostrophe_cells_are_escaped_reversibly(self):
        for text in ['=HYPERLINK("https://example.invalid", "click")', "'literal", '+x', '-1', '@x', ' leading', '\tvalue']:
            with self.subTest(text=text):
                report = make_report(hint=text)
                report['records'][0]['sample_id'] = text
                report['records'][0]['levels'][0]['local']['case_id'] = text
                review.export_csv(report, self.path)
                with self.path.open(encoding='utf-8-sig', newline='') as stream:
                    row = next(csv.DictReader(stream))
                self.assertEqual(row['hint'], "'" + text)
                self.assertEqual(row['sample_id'], "'" + text)
                self.assertEqual(row['case_id'], "'" + text)
                result = review.import_csv(report, self.path)
                self.assertEqual(result['records'][0]['levels'][0]['local']['hint'], text)

    def test_rejects_invalid_duplicate_unknown_missing_and_changed_text(self):
        for transform in [lambda rows: [dict(rows[0], evidence_ok='1')],
                          lambda rows: rows * 2, lambda rows: [dict(rows[0], sample_id='unknown')],
                          lambda rows: [], lambda rows: [dict(rows[0], hint='changed')]]:
            with self.subTest(transform=transform):
                review.export_csv(self.report, self.path)
                self.rewrite(transform)
                with self.assertRaises(ValueError):
                    review.import_csv(self.report, self.path)

    def test_baseline_opt_in_requires_exact_text_and_case(self):
        baseline = make_report(local_review=graded())
        result = review.import_csv(self.report, self.path, baseline)
        self.assertEqual(result['records'][0]['levels'][0]['local']['review'], graded())
        for field in ['hint', 'case_id']:
            baseline = make_report(local_review=graded())
            baseline['records'][0]['levels'][0]['local'][field] += 'changed'
            result = review.import_csv(self.report, self.path, baseline)
            self.assertEqual(result['records'][0]['levels'][0]['local']['review'], dict.fromkeys(review.FIELDS))

