import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from evals.run import request_hint

class EvaluationSampleSelectionTests(unittest.TestCase):
    def test_explicit_samples_does_not_change_default_set(self):
        root=Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as directory:
            samples=Path(directory)/"samples.json"
            output=Path(directory)/"report.json"
            original=json.loads((root/"evals/samples.json").read_text(encoding="utf-8"))
            samples.write_text(json.dumps(original[:1]),encoding="utf-8")
            result=subprocess.run([sys.executable,"-B","-m","evals.run","--samples",str(samples),"--output",str(output)],cwd=root,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr.decode(errors="replace"))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["local_rows"],3)
            self.assertEqual(len(json.loads((root/"evals/samples.json").read_text(encoding="utf-8"))),24)
    def test_compare_timeout_is_forwarded_to_the_hint_client(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 500
        with patch("evals.run.http.client.HTTPConnection", return_value=connection) as factory:
            request_hint(8000, "code", 1, "average", timeout=70)
        self.assertEqual(factory.call_args.kwargs["timeout"], 70)
    def test_fallback_diagnostics_are_preserved_without_model_text(self):
        connection = MagicMock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps({
            "hint": "本地提示", "case_id": "C01", "source": "local", "request_id": "r",
            "fallback_reason": "workflow_failed", "execution_id": "execution-1",
            "cloud_error_code": "AgentArts.102056", "failed_node_id": "node_llm",
            "raw_model_output": "must not be stored",
        }).encode()
        with patch("evals.run.http.client.HTTPConnection", return_value=connection):
            outcome = request_hint(8000, "code", 1)
        self.assertEqual(outcome["outcome"], "fallback")
        self.assertEqual(outcome["fallback_reason"], "workflow_failed")
        self.assertEqual(outcome["execution_id"], "execution-1")
        self.assertEqual(outcome["cloud_error_code"], "AgentArts.102056")
        self.assertEqual(outcome["failed_node_id"], "node_llm")
        self.assertNotIn("raw_model_output", outcome)
