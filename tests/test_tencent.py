import io
import json
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile

from agentarts import get_hint
from exercise import EXERCISE, check_submission
from tools.start import load_env


class TencentHintTests(unittest.TestCase):
    def setUp(self):
        self.result = check_submission(EXERCISE['starter_code'])
        self.env = patch.dict('os.environ', {'AI_PROVIDER':'tencent', 'TENCENT_API_KEY':'test-tencent-key', 'TENCENT_MODEL':'test-model', 'TENCENT_API_URL':'https://api.hunyuan.cloud.tencent.com/v1/chat/completions'}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def response(self, fields):
        return io.BytesIO(json.dumps({'id':'test-execution','choices':[{'finish_reason':'stop','message':{'content':json.dumps(fields,ensure_ascii=False)}}]}).encode())

    @patch('agentarts._OPENER.open')
    def test_tencent_success_evidence_only_and_source(self, upstream):
        upstream.return_value = self.response({'hint':'对照用例数一数元素个数。','case_id':'C01'})
        with self.assertLogs('agentarts',level='INFO') as logs:
            answer=get_hint('average',self.result,2)
        self.assertEqual(answer['source'],'tencent')
        self.assertEqual(answer['execution_id'],'test-execution')
        request=upstream.call_args.args[0]
        body=json.loads(request.data)
        self.assertEqual(body['model'],'test-model')
        self.assertFalse(body['stream'])
        data=json.loads(body['messages'][1]['content'])
        self.assertEqual(data['hint_level'],2)
        self.assertEqual(data['exercise_id'],'average')
        self.assertNotIn(EXERCISE['starter_code'],json.dumps(body))
        self.assertNotIn('test-tencent-key',''.join(logs.output))
        self.assertEqual(request.get_header('Authorization'),'Bearer test-tencent-key')

    @patch('agentarts._OPENER.open')
    def test_missing_config_never_calls_network(self, upstream):
        with patch.dict('os.environ',{'TENCENT_API_KEY':''}):
            answer=get_hint('average',self.result,1)
        self.assertEqual(answer['source'],'local')
        self.assertEqual(answer['fallback_reason'],'not_configured')
        upstream.assert_not_called()

    @patch('agentarts._OPENER.open')
    def test_invalid_outputs_use_same_level_local_hint(self, upstream):
        for fields in ({'hint':'return sum(nums) / len(nums)','case_id':'C01'}, {'hint':'检查元素个数。','case_id':'C99'}, {'hint':[], 'case_id':'C01'}, {'hint':'','case_id':'C01'}):
            upstream.return_value=self.response(fields)
            answer=get_hint('average',self.result,3)
            self.assertEqual(answer['source'],'local')
            self.assertEqual(answer['hint'],self.result['hints'][2])

    @patch('agentarts._OPENER.open',side_effect=TimeoutError)
    def test_timeout_falls_back(self,upstream):
        answer=get_hint('average',self.result,1)
        self.assertEqual(answer['fallback_reason'],'timeout')

    @patch('agentarts._OPENER.open')
    def test_invalid_provider_does_not_call_any_cloud(self,upstream):
        with patch.dict('os.environ',{'AI_PROVIDER':'typo'}):
            answer=get_hint('average',self.result,1)
        self.assertEqual(answer['fallback_reason'],'invalid_provider')
        upstream.assert_not_called()

    @patch('agentarts._OPENER.open')
    def test_invalid_response_and_oversized_body(self,upstream):
        for body in (b'not json',b'[]',b'{}',b'x'*131073):
            upstream.return_value=io.BytesIO(body)
            self.assertEqual(get_hint('average',self.result,1)['source'],'local')

    @patch('agentarts._OPENER.open')
    def test_tencent_endpoint_requires_https(self,upstream):
        with patch.dict('os.environ',{'TENCENT_API_URL':'http://example.test/chat/completions'}):
            answer=get_hint('average',self.result,1)
        self.assertEqual(answer['source'],'local')
        upstream.assert_not_called()

    def test_startup_accepts_provider_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'.env'
            path.write_text('AI_PROVIDER=tencent\nTENCENT_MODEL=test-model\nTENCENT_API_KEY=\nTENCENT_API_URL=https://api.hunyuan.cloud.tencent.com/v1/chat/completions\n',encoding='utf-8')
            env={}
            load_env(path,env)
            self.assertEqual(env['AI_PROVIDER'],'tencent')


class TencentEvaluationTests(unittest.TestCase):
    @patch('evals.run.http.client.HTTPConnection')
    def test_evaluation_preserves_tencent_source(self, connection):
        from evals.run import request_hint
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({'hint':'检查元素个数。','case_id':'C01','source':'tencent','request_id':'request-1'}).encode()
        outcome = request_hint(8000, 'sample', 1)
        self.assertEqual(outcome['source'], 'tencent')
        self.assertEqual(outcome['outcome'], 'cloud')

    @patch('agentarts._OPENER.open')
    def test_http_error_falls_back_without_exposing_key(self, upstream):
        from urllib.error import HTTPError
        upstream.side_effect = HTTPError('https://example.test', 401, 'unauthorized', {}, io.BytesIO(b''))
        result = check_submission(EXERCISE['starter_code'])
        with patch.dict('os.environ', {'AI_PROVIDER':'tencent','TENCENT_API_KEY':'private-test-key','TENCENT_MODEL':'test-model'}, clear=True):
            with self.assertLogs('agentarts',level='INFO') as logs:
                answer = get_hint('average',result,2)
        self.assertEqual(answer['fallback_reason'],'http_error')
        self.assertEqual(answer['hint'],result['hints'][1])
        self.assertNotIn('private-test-key', ''.join(logs.output))

    @patch('agentarts._OPENER.open')
    def test_incomplete_completion_is_rejected(self, upstream):
        body = {'choices':[{'finish_reason':'length','message':{'content':'{}'}}]}
        upstream.return_value = io.BytesIO(json.dumps(body).encode())
        result = check_submission(EXERCISE['starter_code'])
        with patch.dict('os.environ', {'AI_PROVIDER':'tencent','TENCENT_API_KEY':'test-key','TENCENT_MODEL':'test-model'},clear=True):
            answer = get_hint('average',result,1)
        self.assertEqual(answer['fallback_reason'],'invalid_response')
