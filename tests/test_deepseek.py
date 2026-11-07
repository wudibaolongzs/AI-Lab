import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agentarts import get_hint
from exercise import EXERCISE, check_submission
from tools.start import load_env


class DeepSeekHintTests(unittest.TestCase):
    def setUp(self):
        self.result = check_submission(EXERCISE['starter_code'])
        self.env = patch.dict('os.environ', {
            'AI_PROVIDER': 'deepseek',
            'DEEPSEEK_API_URL': 'https://api.deepseek.com/chat/completions',
            'DEEPSEEK_API_KEY': 'test-deepseek-key',
            'DEEPSEEK_MODEL': 'deepseek-chat',
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, fields):
        return io.BytesIO(json.dumps({
            'id': 'deepseek-execution',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(fields, ensure_ascii=False)}}],
        }).encode())

    @patch('agentarts._OPENER.open')
    def test_deepseek_success_marks_source_and_requests_json(self, upstream):
        upstream.return_value = self.response({'hint': '核对参与平均值计算的元素数量。', 'case_id': 'C01'})
        with self.assertLogs('agentarts', level='INFO') as logs:
            answer = get_hint('average', self.result, 2)
        self.assertEqual(answer['source'], 'deepseek')
        self.assertEqual(answer['execution_id'], 'deepseek-execution')
        request = upstream.call_args.args[0]
        body = json.loads(request.data)
        self.assertEqual(body['model'], 'deepseek-chat')
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertFalse(body['stream'])
        self.assertNotIn(EXERCISE['starter_code'], json.dumps(body))
        self.assertEqual(request.get_header('Authorization'), 'Bearer test-deepseek-key')
        self.assertNotIn('test-deepseek-key', ''.join(logs.output))

    @patch('agentarts._OPENER.open')
    def test_missing_key_never_calls_network(self, upstream):
        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': ''}):
            answer = get_hint('average', self.result, 1)
        self.assertEqual(answer['source'], 'local')
        self.assertEqual(answer['fallback_reason'], 'not_configured')
        upstream.assert_not_called()

    @patch('agentarts._OPENER.open')
    def test_non_https_endpoint_is_rejected_without_a_request(self, upstream):
        with patch.dict('os.environ', {'DEEPSEEK_API_URL': 'http://api.deepseek.com/chat/completions'}):
            answer = get_hint('average', self.result, 1)
        self.assertEqual(answer['fallback_reason'], 'invalid_endpoint')
        upstream.assert_not_called()

    @patch('agentarts._OPENER.open')
    def test_invalid_outputs_use_same_level_local_hint(self, upstream):
        for fields in ({'hint': 'return sum(nums) / len(nums)', 'case_id': 'C01'},
                       {'hint': '检查元素个数。', 'case_id': 'C99'},
                       {'hint': [], 'case_id': 'C01'},
                       {'hint': '', 'case_id': 'C01'}):
            upstream.return_value = self.response(fields)
            answer = get_hint('average', self.result, 3)
            self.assertEqual(answer['source'], 'local')
            self.assertEqual(answer['hint'], self.result['hints'][2])

    @patch('agentarts._OPENER.open')
    def test_incomplete_or_non_json_completion_is_rejected(self, upstream):
        bodies = (b'not json', b'[]', b'{}',
                  json.dumps({'choices': [{'finish_reason': 'length', 'message': {'content': '{}'}}]}).encode())
        for body in bodies:
            upstream.return_value = io.BytesIO(body)
            self.assertEqual(get_hint('average', self.result, 1)['source'], 'local')

    def test_startup_accepts_deepseek_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text(
                'AI_PROVIDER=deepseek\nDEEPSEEK_MODEL=deepseek-chat\nDEEPSEEK_API_KEY=\n'
                'DEEPSEEK_API_URL=https://api.deepseek.com/chat/completions\n',
                encoding='utf-8')
            environment = {}
            load_env(path, environment)
            self.assertEqual(environment['AI_PROVIDER'], 'deepseek')
            self.assertEqual(environment['DEEPSEEK_MODEL'], 'deepseek-chat')


class DeepSeekEvaluationTests(unittest.TestCase):
    @patch('evals.run.http.client.HTTPConnection')
    def test_evaluation_preserves_deepseek_source(self, connection):
        from evals.run import request_hint
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({
            'hint': '检查元素个数。', 'case_id': 'C01', 'source': 'deepseek', 'request_id': 'request-1',
        }).encode()
        outcome = request_hint(8000, 'sample', 1)
        self.assertEqual(outcome['source'], 'deepseek')
        self.assertEqual(outcome['outcome'], 'cloud')