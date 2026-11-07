"""Checks for the endpoint probe's own logic, so its verdicts can be trusted under pressure.

The probe is the tool a teammate reaches for when every hint falls back, so these tests pin
down the parts it reasons about: the payload it sends, how it reads an event stream, and the
advice it prints for each failure shape.
"""

import io
import json
from contextlib import redirect_stdout
import time
import unittest
from unittest.mock import patch

from exercise import EXERCISES
from tools import probe_agentarts as probe


def stream_of(events):
    return io.BytesIO("".join(f"data: {json.dumps(event, ensure_ascii=False)}\r\n\r\n"
                              for event in events).encode("utf-8"))


def deadline():
    return time.monotonic() + 5


class ProbeTests(unittest.TestCase):
    def describe(self, events):
        out = io.StringIO()
        with redirect_stdout(out):
            probe.describe_stream(events, 12)
        return out.getvalue()

    def test_main_loads_the_local_env_file_before_checking_configuration(self):
        with patch.dict("os.environ", {}, clear=True), \
                patch("tools.probe_agentarts.load_env") as load_env, \
                patch("tools.probe_agentarts.check_configuration", return_value=False), \
                patch("sys.argv", ["probe_agentarts.py"]), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(probe.main(), 2)
        load_env.assert_called_once()

    def test_narrowed_scope_keeps_the_documented_three_fields(self):
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": "average"}, clear=True):
            body, result, failed = probe.payload_for("average", 2)
        self.assertEqual(set(body["inputs"]), {"exercise_title", "evidence_json", "hint_level"})
        self.assertEqual(body["inputs"]["hint_level"], 2)
        self.assertEqual(json.loads(body["inputs"]["evidence_json"])["cases"], failed)
        self.assertEqual(failed[0]["id"], "C01")
        self.assertEqual(result["status"], "failed")

    def test_default_scope_adds_the_exercise_id(self):
        with patch.dict("os.environ", {}, clear=True):
            body, _, _ = probe.payload_for("sum", 1)
        self.assertEqual(body["inputs"]["exercise_id"], "sum")
        self.assertEqual(body["inputs"]["exercise_title"], EXERCISES["sum"]["title"])

    def test_payload_adds_exercise_id_in_multi_exercise_mode(self):
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": "average,sum,count"}):
            body, _, _ = probe.payload_for("sum", 1)
        self.assertEqual(body["inputs"]["exercise_id"], "sum")
        self.assertEqual(body["inputs"]["exercise_title"], EXERCISES["sum"]["title"])

    def test_collect_events_stops_at_the_terminal_event_and_flags_broken_json(self):
        events = probe.collect_events(stream_of([
            {"event": "node_started", "data": {}},
            {"event": "workflow_finished", "data": {"status": {"code": 1, "desc": "succeeded"}}},
            {"event": "message", "data": {"text": "之后的事件不该被读取"}},
        ]), deadline())
        self.assertEqual([event["event"] for event in events], ["node_started", "workflow_finished"])
        broken = probe.collect_events(io.BytesIO(b"data: {oops\r\n\r\n"), deadline())
        self.assertEqual(broken[0]["event"], "!broken-json")

    def test_empty_stream_is_reported_as_not_an_event_stream(self):
        self.assertIn("没有收到任何 data: 事件", self.describe([]))

    def test_error_events_point_at_the_console_execution_record(self):
        output = self.describe([{"event": "error", "data": {"error_code": "MOCK", "message": "节点失败"}}])
        self.assertIn("[FAIL]", output)
        self.assertIn("execution_id", output)

    def test_missing_user_fields_explains_the_end_node_fix(self):
        events = [{"event": "workflow_finished", "data": {"status": {"code": 1, "desc": "succeeded"},
                                                          "outputs": {"responseContent": "只有文本"}}}]
        output = self.describe(events)
        self.assertIn("outputs.user_fields 缺失或为空", output)
        self.assertIn("结束节点", output)

    def test_successful_stream_is_summarised_as_passing(self):
        events = [{"event": "workflow_finished", "data": {
            "status": {"code": 1, "desc": "succeeded"}, "execution_id": "e-1",
            "outputs": {"user_fields": {"hint": "检查分母用的是哪个量。", "case_id": "C01"}}}}]
        output = self.describe(events)
        self.assertIn("[PASS] user_fields", output)
        self.assertNotIn("[FAIL]", output)
        self.assertNotIn("[WARN]", output)

    def test_configuration_problems_are_reported_before_any_request(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertFalse(probe.check_configuration("", ""))
            self.assertFalse(probe.check_configuration("http://192.168.1.9:8931/runtimes/a/invocations", "key"))
        text = out.getvalue()
        self.assertIn("未配置", text)
        self.assertIn("不安全", text)

    def test_key_never_appears_in_probe_output(self):
        out = io.StringIO()
        with redirect_stdout(out):
            probe.check_configuration("https://example.test/runtimes/a/invocations", "super-secret-key")
        self.assertNotIn("super-secret-key", out.getvalue())


if __name__ == "__main__":
    unittest.main()
