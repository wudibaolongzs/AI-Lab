import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

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
