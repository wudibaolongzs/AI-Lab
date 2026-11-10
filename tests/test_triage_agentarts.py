import json
import tempfile
import unittest
from pathlib import Path

from tools.triage_agentarts import collect, main, summarise


def line(source, reason, code=None, node=None, execution="execution-example"):
    return json.dumps({"request_id": "r", "source": source, "fallback_reason": reason,
                       "cloud_error_code": code, "failed_node_id": node,
                       "execution_id": execution, "elapsed_ms": 1200})


class TriageTests(unittest.TestCase):
    def test_only_workflow_failures_are_collected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.jsonl"
            path.write_text("\n".join([
                line("local", "workflow_failed", "AgentArts.102056", "node_llm"),
                line("local", "timeout"),
                line("agentarts", None),
                line("local", "workflow_failed", "AgentArts.102056", "node_1794225680834"),
            ]), encoding="utf-8")
            rows = collect([path])
        self.assertEqual(len(rows), 2)
        summary = summarise(rows)
        self.assertEqual(summary["by_code"]["AgentArts.102056"], 2)
        self.assertEqual(summary["by_node"]["node_llm"], 1)

    def test_missing_failures_exit_with_two(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.jsonl"
            path.write_text(line("agentarts", None), encoding="utf-8")
            self.assertEqual(main([str(path)]), 2)


if __name__ == "__main__":
    unittest.main()