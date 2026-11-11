import json
import tempfile
import unittest
from pathlib import Path

from tools.check_retest import collect, expected_positions, main, summarise


def report(levels):
    records = {}
    for sample, level, endpoint in levels:
        records.setdefault(sample, []).append({'level': level, 'endpoint': endpoint})
    return {'records': [{'sample_id': sample, 'levels': rows} for sample, rows in records.items()]}


class RetestCheckTests(unittest.TestCase):
    def samples(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'samples.json'
        path.write_text(json.dumps([{'id': 'SU3'}, {'id': 'CO2'}]), encoding='utf-8')
        return path

    def test_all_cloud_positions_pass(self):
        expected = expected_positions(self.samples())
        data = report([(sample, level, {'outcome': 'cloud', 'elapsed_ms': 1000})
                       for sample in ('SU3', 'CO2') for level in (1, 2, 3)])
        summary = summarise(collect(data, expected), expected)
        self.assertTrue(summary['passed'])
        self.assertEqual(summary['cloud'], 6)

    def test_workflow_failure_fails_and_keeps_execution_id(self):
        path = self.samples()
        expected = expected_positions(path)
        data = report([(sample, level, {'outcome': 'cloud'})
                       for sample in ('SU3', 'CO2') for level in (1, 2, 3)])
        for record in data['records']:
            if record['sample_id'] == 'CO2':
                record['levels'][1]['endpoint'] = {
                    'outcome': 'fallback', 'fallback_reason': 'workflow_failed',
                    'execution_id': 'execution-1', 'cloud_error_code': 'AgentArts.102056',
                    'failed_node_id': 'node_llm',
                }
        rows = collect(data, expected)
        summary = summarise(rows, expected)
        self.assertFalse(summary['passed'])
        self.assertEqual(summary['fallback'], 1)
        failed = next(row for row in rows if row['outcome'] == 'fallback')
        self.assertEqual(failed['execution_id'], 'execution-1')
        self.assertEqual(failed['failed_node_id'], 'node_llm')

    def test_missing_positions_fail_and_main_exits_one(self):
        path = self.samples()
        expected = expected_positions(path)
        data = report([('SU3', level, {'outcome': 'cloud'}) for level in (1, 2, 3)])
        summary = summarise(collect(data, expected), expected)
        self.assertFalse(summary['passed'])
        self.assertEqual(len(summary['missing']), 3)
        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / 'report.json'
            report_path.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(main([str(report_path), '--samples', str(path)]), 1)

    def test_missing_input_exits_two(self):
        self.assertEqual(main(['definitely-not-here.json']), 2)


if __name__ == '__main__':
    unittest.main()