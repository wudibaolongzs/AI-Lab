import io
import json
import unittest
from unittest.mock import patch
import agentarts
from exercise import EXERCISES, check_submission

class WorkflowFailureDiagnosticsTests(unittest.TestCase):
    def test_failed_workflow_keeps_safe_metadata_and_never_logs_error_text(self):
        events = [
            {'event':'error','data':{'node_id':'node_llm','error_code':'AgentArts.100025','message':'secret-in-model-error'}},
            {'event':'workflow_finished','data':{'status':{'code':2,'desc':'failed'},'execution_id':'execution-example','error_code':100025,'error_message':'secret-in-model-error'}},
            {'event':'end'}]
        stream=io.BytesIO(''.join('data: '+json.dumps(e)+'\n\n' for e in events).encode())
        result=check_submission(EXERCISES['average']['starter_code'],'average')
        with patch.dict('os.environ',{'AI_PROVIDER':'agentarts','AGENTARTS_WORKFLOW_URL':'https://example.test/invocations','AGENTARTS_API_KEY':'synthetic-key','AGENTARTS_EXERCISES':'average','AI_HINT_PROTECTION':'0'},clear=True), patch('agentarts._OPENER.open',return_value=stream), self.assertLogs('agentarts',level='INFO') as logs:
            reply=agentarts.get_hint('average',result,1)
        self.assertEqual(reply['source'],'local')
        self.assertEqual(reply['fallback_reason'],'workflow_failed')
        self.assertEqual(reply['execution_id'],'execution-example')
        self.assertEqual(reply['cloud_error_code'],'AgentArts.100025')
        self.assertEqual(reply['failed_node_id'],'node_llm')
        self.assertNotIn('secret-in-model-error',str(reply)+str(logs.output))
        self.assertIn('AgentArts.100025',str(logs.output))

    def test_error_event_alone_fails_closed(self):
        stream=io.BytesIO(b'data: {"event":"error","data":{"error_code":"bad key with spaces","node_id":"unsafe node"}}\n\n')
        with self.assertRaises(agentarts.WorkflowFailure) as caught:
            agentarts._workflow_result(stream,float('inf'))
        self.assertIsNone(caught.exception.code)
        self.assertIsNone(caught.exception.node_id)
