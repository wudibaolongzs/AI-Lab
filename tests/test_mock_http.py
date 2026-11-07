"""One real socket round trip between agentarts.py and the mock runtime.

The offline contract tests feed hand-built bytes to the parser and the 26-second harness in
``tools/verify_agentarts.py`` drives whole processes. This file sits between them: it serves
the mock on a loopback port inside the test process, so plain ``unittest discover`` catches
request-shape, header and response-framing regressions without spawning anything.
"""

import http.client
import json
import os
import socket
import threading
import unittest
from unittest.mock import patch

import agentarts
from exercise import EXERCISES, check_submission
from tools.mock_agentarts import MockServer


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
class LiveMockRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = []
        cls.server = MockServer(("127.0.0.1", 0), mode="ok", api_key="live-test-key", log=cls.records.append)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/runtimes/ai-lab-average/invocations"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def setUp(self):
        self.result = check_submission(EXERCISES["average"]["starter_code"], "average")
        self.records.clear()

    def env(self, **overrides):
        base = {"AGENTARTS_WORKFLOW_URL": self.url, "AGENTARTS_API_KEY": "live-test-key"}
        base.update(overrides)
        return patch.dict("os.environ", base)

    def test_cloud_hint_survives_a_real_socket_round_trip(self):
        with self.env(), self.assertLogs("agentarts", level="INFO") as logs:
            reply = agentarts.get_hint("average", self.result, 2)
        self.assertEqual(reply["source"], "agentarts")
        self.assertEqual(reply["case_id"], "C01")
        self.assertIn("第 3 行", reply["hint"])
        self.assertIn("null", logs.output[0])  # fallback_reason stays null on a cloud hit
        self.assertEqual(len(self.records), 1)
        record = self.records[0]
        self.assertEqual(record["request_id"], reply["request_id"])
        self.assertEqual(record["exercise"], "average")
        self.assertEqual(record["hint_level"], 2)

    def test_wrong_runtime_key_falls_back_to_the_local_hint(self):
        with self.env(AGENTARTS_API_KEY="not-the-runtime-key"), self.assertLogs("agentarts", level="INFO") as logs:
            reply = agentarts.get_hint("average", self.result, 1)
        self.assertEqual(reply["source"], "local")
        self.assertEqual(reply["hint"], self.result["hints"][0])
        self.assertIn("http_error", logs.output[0])
        self.assertEqual(self.records, [])  # rejected before the workflow ever ran

    def test_rejected_keys_always_report_the_runtime_status(self):
        """Answering before the request body is drained once turned http_error into connection_error."""
        for attempt in range(8):
            with self.env(AGENTARTS_API_KEY="not-the-runtime-key"), self.assertLogs("agentarts", level="INFO") as logs:
                reply = agentarts.get_hint("average", self.result, 1)
            self.assertEqual(reply["source"], "local", f"第 {attempt + 1} 次")
            self.assertIn("http_error", logs.output[0], f"第 {attempt + 1} 次：{logs.output[0]}")
        self.assertEqual(self.records, [])

    def test_oversized_invocation_body_is_rejected_without_losing_the_answer(self):
        """The mock has to answer 413 after draining a body it refuses to run."""
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        self.addCleanup(connection.close)
        body = json.dumps({"inputs": {"exercise_title": "x" * 200_000, "evidence_json": "{}", "hint_level": 1}})
        connection.request("POST", "/runtimes/ai-lab-average/invocations", body,
                           {"Authorization": "Bearer live-test-key", "Content-Type": "application/json"})
        response = connection.getresponse()
        self.assertEqual(response.status, 413)
        self.assertIn("过大", json.loads(response.read().decode("utf-8"))["error"])
        self.assertEqual(self.records, [])

    def test_a_caller_that_declares_a_body_it_never_sends_still_gets_an_answer(self):
        """Draining before the reply needs a socket timeout, or a worker thread is held open forever."""
        from tools.mock_agentarts import Handler

        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=5)
        self.addCleanup(connection.close)
        with patch.object(Handler, "timeout", 0.2):
            connection.putrequest("POST", "/runtimes/ai-lab-average/invocations")
            connection.putheader("Authorization", "Bearer wrong-key")
            connection.putheader("Content-Type", "application/json")
            connection.putheader("Content-Length", "4096")
            connection.endheaders()
            response = connection.getresponse()
        self.assertEqual(response.status, 401)
        self.assertIn("API Key", json.loads(response.read().decode("utf-8"))["error"])
        self.assertEqual(self.records, [])

    def test_closed_port_falls_back_without_raising(self):
        url = f"http://127.0.0.1:{free_port()}/runtimes/ai-lab-average/invocations"
        with self.env(AGENTARTS_WORKFLOW_URL=url), self.assertLogs("agentarts", level="INFO") as logs:
            reply = agentarts.get_hint("average", self.result, 3)
        self.assertEqual(reply["hint"], self.result["hints"][2])
        self.assertIn("connection_error", logs.output[0])

    def test_multi_exercise_call_carries_the_exercise_id(self):
        count = check_submission(EXERCISES["count"]["starter_code"], "count")
        with self.env(AGENTARTS_EXERCISES="average,sum,count"):
            reply = agentarts.get_hint("count", count, 1)
        self.assertEqual(reply["source"], "agentarts")
        self.assertEqual(reply["case_id"], "N01")
        self.assertIn("占 3 个位置", reply["hint"])
        self.assertNotIn("分母", reply["hint"], "计数题的模拟提示不能借平均值题的说法")
        self.assertEqual(self.records[0]["exercise"], "count")


if __name__ == "__main__":
    unittest.main()
