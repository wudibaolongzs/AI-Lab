import io
import json
import unittest
from unittest.mock import patch

from agentarts import get_hint
from exercise import EXERCISE, EXERCISES, check_submission


class AgentArtsHintTests(unittest.TestCase):
    def test_missing_config_explains_local_fallback_without_exposing_secrets(self):
        result = check_submission(EXERCISE["starter_code"])
        with patch.dict("os.environ", {"AGENTARTS_API_KEY": "", "AGENTARTS_WORKFLOW_URL": ""}):
            response = get_hint("average", result, 1)
        self.assertEqual(response["fallback_reason"], "not_configured")
        self.assertIsNone(response["execution_id"])
        self.assertEqual(response["source"], "local")

    def setUp(self):
        self.result = check_submission(EXERCISE["starter_code"])
        self.env = patch.dict("os.environ", {
            "AGENTARTS_WORKFLOW_URL": "https://example.test/runtimes/average/invocations",
            "AGENTARTS_API_KEY": "test-runtime-key",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def stream(self, hint, case_id="C01", status="succeeded"):
        events = [
            {"event": "message", "data": {"text": "不应显示的中间输出"}},
            {"event": "workflow_finished", "data": {
                "status": {"code": 1, "desc": status},
                "execution_id": "example-execution",
                "outputs": {"user_fields": {"hint": hint, "case_id": case_id}},
            }},
        ]
        return io.BytesIO("".join(f"data: {json.dumps(event)}\r\n\r\n" for event in events).encode())

    @patch("agentarts._OPENER.open")
    def test_narrowed_scope_uses_published_final_event_and_sends_only_evidence(self, open_stream):
        hint = "对照失败用例，数一数列表中实际有多少元素。"
        open_stream.return_value = self.stream(hint)
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": "average"}):
            with self.assertLogs("agentarts", level="INFO") as logs:
                response = get_hint("average", self.result, 1)
        self.assertEqual(response["source"], "agentarts")
        self.assertEqual(response["hint"], hint)
        self.assertEqual(response["case_id"], "C01")
        request = open_stream.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-runtime-key")
        self.assertEqual(request.get_header("X-request-id"), response["request_id"])
        inputs = json.loads(request.data)["inputs"]
        self.assertEqual(set(inputs), {"exercise_title", "evidence_json", "hint_level"})
        self.assertEqual(inputs["hint_level"], 1)
        evidence = json.loads(inputs["evidence_json"])
        self.assertEqual(evidence["cases"], [case for case in self.result["cases"] if case["status"] != "passed"])
        self.assertEqual(evidence["diagnosis"], self.result["diagnosis"])
        self.assertIn("example-execution", logs.output[0])
        self.assertNotIn("test-runtime-key", logs.output[0])
        self.assertNotIn(hint, logs.output[0])

    @patch("agentarts._OPENER.open")
    def test_wrong_case_waiting_and_code_outputs_fall_back_at_requested_level(self, open_stream):
        for stream in (
            self.stream("检查除数。", case_id="C99"),
            self.stream("检查除数。", status="waiting"),
            self.stream("使用 sum(nums) / len(nums) 计算。"),
            self.stream("请写sum(nums)/len(nums)。"),
            self.stream("return total / len(nums)"),
            self.stream("  "),
            io.BytesIO(b"data: not-json\n\n"),
        ):
            with self.subTest(stream=stream):
                open_stream.return_value = stream
                response = get_hint("average", self.result, 2)
                self.assertEqual(response["source"], "local")
                self.assertEqual(response["hint"], self.result["hints"][1])

    @patch("agentarts._OPENER.open", side_effect=TimeoutError)
    def test_timeout_returns_local_hint(self, open_stream):
        self.assertEqual(get_hint("average", self.result, 3)["hint"], self.result["hints"][2])
        open_stream.assert_called_once()

    @patch("agentarts._OPENER.open")
    def test_loopback_http_is_allowed_for_local_verification(self, open_stream):
        hint = "对照失败用例，数一数列表中实际有多少元素。"
        open_stream.return_value = self.stream(hint)
        with patch.dict("os.environ", {
            "AGENTARTS_WORKFLOW_URL": "http://127.0.0.1:8931/runtimes/ai-lab/invocations"}):
            response = get_hint("average", self.result, 1)
        self.assertEqual(response["source"], "agentarts")
        self.assertEqual(response["hint"], hint)
        open_stream.assert_called_once()

    @patch("agentarts._OPENER.open")
    def test_cleartext_endpoints_never_reach_the_network(self, open_stream):
        for url in ("http://192.168.1.20:8931/runtimes/ai-lab/invocations",
                    "http://example.test/runtimes/ai-lab/invocations",
                    "ftp://127.0.0.1/runtimes/ai-lab/invocations",
                    "https://user:pw@127.0.0.1/runtimes/ai-lab/invocations"):
            with self.subTest(url=url), patch.dict("os.environ", {"AGENTARTS_WORKFLOW_URL": url}):
                with self.assertLogs("agentarts", level="INFO") as logs:
                    response = get_hint("average", self.result, 1)
            self.assertEqual(response["source"], "local")
            self.assertEqual(response["hint"], self.result["hints"][0])
            self.assertIn("invalid_endpoint", logs.output[0])
        open_stream.assert_not_called()

    @patch("agentarts._OPENER.open")
    def test_multi_exercise_mode_sends_exercise_id_and_covers_other_exercises(self, open_stream):
        hint = "对照失败用例，数一数列表里有多少个位置。"
        open_stream.return_value = self.stream(hint, case_id="N01")
        result = check_submission(EXERCISES["count"]["starter_code"], "count")
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": "average, sum, count"}):
            response = get_hint("count", result, 1)
        self.assertEqual(response["source"], "agentarts")
        self.assertEqual(response["case_id"], "N01")
        inputs = json.loads(open_stream.call_args.args[0].data)["inputs"]
        self.assertEqual(set(inputs), {"exercise_title", "evidence_json", "hint_level", "exercise_id"})
        self.assertEqual(inputs["exercise_id"], "count")
        self.assertEqual(inputs["exercise_title"], EXERCISES["count"]["title"])

    @patch("agentarts._OPENER.open")
    def test_default_scope_sends_the_exercise_id_for_the_average_exercise(self, open_stream):
        hint = "对照失败用例，数一数列表中实际有多少元素。"
        open_stream.return_value = self.stream(hint)
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": ""}):
            response = get_hint("average", self.result, 1)
        self.assertEqual(response["source"], "agentarts")
        inputs = json.loads(open_stream.call_args.args[0].data)["inputs"]
        self.assertEqual(set(inputs), {"exercise_title", "evidence_json", "hint_level", "exercise_id"})
        self.assertEqual(inputs["exercise_id"], "average")

    @patch("agentarts._OPENER.open")
    def test_unknown_exercise_list_falls_back_to_the_all_exercise_default(self, open_stream):
        hint = "对照失败用例，数一数列表中实际有多少元素。"
        open_stream.side_effect = lambda *args, **kwargs: self.stream(hint)
        with patch.dict("os.environ", {"AGENTARTS_EXERCISES": "nonexistent"}):
            self.assertEqual(get_hint("average", self.result, 1)["source"], "agentarts")
            self.assertEqual(get_hint("count", self.result, 1)["source"], "agentarts")
        self.assertEqual(open_stream.call_count, 2)
        self.assertIn("exercise_id", json.loads(open_stream.call_args.args[0].data)["inputs"])

    @patch("agentarts._OPENER.open")
    def test_missing_config_never_invokes_cloud(self, open_stream):
        with patch.dict("os.environ", {"AGENTARTS_API_KEY": ""}):
            for exercise_id in ("average", "sum", "count"):
                self.assertEqual(get_hint(exercise_id, self.result, 1)["source"], "local")
        open_stream.assert_not_called()
