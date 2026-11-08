import http.client
import json
import select
import socket
import os
import threading
import unittest
from unittest.mock import patch


@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from app import create_server

        cls.server = create_server(0)
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.addClassCleanup(cls.server.server_close)
        cls.addClassCleanup(cls.worker.join, 5)
        cls.addClassCleanup(cls.server.shutdown)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            connection.request(method, path, body, headers or {})
            response = connection.getresponse()
            return response.status, response.read().decode("utf-8")
        finally:
            connection.close()

    def check(self, body, path="/api/check"):
        status, response = self.request(
            "POST", path, json.dumps(body), {"Content-Type": "application/json"}
        )
        return status, json.loads(response)

    def start_partial_post(self, path, content_type, length):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        self.addCleanup(connection.close)
        connection.putrequest("POST", path)
        connection.putheader("Content-Type", content_type)
        connection.putheader("Content-Length", str(length))
        connection.endheaders()
        return connection

    def test_browser_page_and_exercise_are_served(self):
        status, page = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("AI-Lab", page)
        status, body = self.request("GET", "/api/exercise")
        self.assertEqual(status, 200)
        self.assertIn("def average(nums):", json.loads(body)["starter_code"])

    def test_failed_attempt_can_be_revised_and_retested(self):
        _, body = self.request("GET", "/api/exercise")
        starter = json.loads(body)["starter_code"]
        status, first = self.check({"code": starter})
        self.assertEqual(status, 200)
        self.assertEqual(first["status"], "failed")
        self.assertEqual(len(first["hints"]), 3)
        sample = next(case for case in first["cases"] if case["input"] == [10, 20, 30, 40])
        self.assertEqual(sample["expected"], 25.0)
        self.assertAlmostEqual(sample["actual"], 100 / 3)
        status, second = self.check({"code": starter.replace("(len(nums) - 1)", "len(nums)")})
        self.assertEqual(status, 200)
        self.assertEqual(second["status"], "passed")
        self.assertEqual(second["passed"], second["total"])
        self.assertEqual(second["hints"], [])

    def test_catalog_exercises_use_their_own_cases_and_function_names(self):
        status, body = self.request("GET", "/api/exercises")
        self.assertEqual(status, 200)
        exercises = json.loads(body)
        self.assertEqual([item["id"] for item in exercises[:8]], ["average", "sum", "count", "double_sum", "shifted_average", "total_with_fee", "pair_count", "average_with_zero"])
        self.assertEqual(len(exercises), 28)

        expressions = ("sum(nums)", "len(nums)", "sum(nums)*2", "sum(nums)/len(nums)+2",
                       "sum(nums)+5", "len(nums)*2", "sum(nums)/(len(nums)+1)")
        for exercise, expression in zip(exercises[1:], expressions):
            with self.subTest(exercise=exercise["id"]):
                submission = {"exercise_id": exercise["id"], "code": exercise["starter_code"]}
                status, result = self.check(submission)
                self.assertEqual(status, 200)
                self.assertEqual(result["status"], "failed")
                self.assertEqual(len(result["hints"]), 3)

                submission["code"] = f"{exercise['signature']}\n    return {expression}"
                _, result = self.check(submission)
                self.assertEqual(result["status"], "passed")
                self.assertEqual(result["passed"], result["total"])

                submission["code"] = f"def average(nums):\n    return {expression}"
                _, result = self.check(submission)
                self.assertEqual(result["status"], "invalid")
                self.assertIn(exercise["signature"], result["diagnosis"]["message"])

    def test_unknown_or_malformed_exercise_id_is_a_client_error(self):
        for exercise_id in ("unknown", "", [], None):
            with self.subTest(exercise_id=exercise_id):
                status, result = self.check({"code": "def average(nums):\n    return 0", "exercise_id": exercise_id})
                self.assertEqual(status, 400)
                self.assertIn("error", result)

    def test_bad_payload_is_a_client_error(self):
        for body in ({}, {"code": 42}, ["source"]):
            with self.subTest(body=body):
                status, response = self.check(body)
                self.assertEqual(status, 400)
                self.assertIn("error", response)

    def test_oversized_payload_is_rejected(self):
        status, response = self.check({"code": "x" * 20000})
        self.assertEqual(status, 413)
        self.assertIn("error", response)

    def test_repeated_oversized_payloads_always_reach_the_client(self):
        """Replying while the client is still writing used to reset the socket on Windows now and then."""
        for attempt in range(8):
            status, response = self.check({"code": "x" * 20000})
            self.assertEqual(status, 413, f"第 {attempt + 1} 次")
            self.assertIn("过长", response["error"], f"第 {attempt + 1} 次")

    def test_a_far_too_large_body_is_drained_before_the_rejection(self):
        """Draining only as much as the size cap used to leave the rest of a 200 KB body unread."""
        from app import DRAIN_CEILING, MAX_REQUEST_BYTES

        self.assertGreater(DRAIN_CEILING, MAX_REQUEST_BYTES, "the drain must out-reach the size cap")
        for attempt in range(4):
            status, response = self.check({"code": "x" * 200_000})
            self.assertEqual(status, 413, f"第 {attempt + 1} 次")
            self.assertIn("过长", response["error"], f"第 {attempt + 1} 次")

    def test_normal_submission_still_works_after_an_oversized_one(self):
        self.check({"code": "x" * 20000})
        status, response = self.check({"code": "def average(nums):\n    return sum(nums) / len(nums)\n"})
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "passed")

    def test_null_byte_returns_structured_syntax_feedback(self):
        status, response = self.check({"code": "\x00"})
        self.assertEqual(status, 200)
        self.assertEqual(response["status"], "invalid")
        self.assertEqual(response["diagnosis"]["kind"], "syntax")

    def test_unknown_route_and_non_json_body_are_rejected(self):
        status, _ = self.request("GET", "/app.py")
        self.assertEqual(status, 404)
        status, _ = self.request("POST", "/api/check", "code=abc")
        self.assertEqual(status, 415)

    def test_non_json_requests_wait_for_the_entire_body_before_rejecting(self):
        for path in ("/api/check", "/api/hint"):
            with self.subTest(path=path):
                connection = self.start_partial_post(path, "text/plain", 8)
                connection.send(b"code=")
                readable, _, _ = select.select([connection.sock], [], [], 0.25)
                self.assertEqual(readable, [], "server responded before receiving the entire body")
                connection.send(b"abc")
                response = connection.getresponse()
                self.assertEqual(response.status, 415)
                self.assertIn("error", json.load(response))

    def test_oversized_non_json_requests_are_rejected_before_body_is_sent(self):
        connection = self.start_partial_post("/api/hint", "text/plain", 12289)
        response = connection.getresponse()
        self.assertEqual(response.status, 413)
        self.assertIn("error", json.load(response))

    def test_short_body_is_a_client_error_even_if_received_prefix_is_valid_json(self):
        body = b'{"code":"def average(nums):\\n    return 0"}'
        connection = self.start_partial_post("/api/check", "application/json", len(body) + 1)
        connection.send(body)
        connection.sock.shutdown(socket.SHUT_WR)
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn("error", json.load(response))

    def test_request_body_timeout_returns_structured_408(self):
        from app import Handler

        with patch.object(Handler, "timeout", 0.1):
            connection = self.start_partial_post("/api/check", "application/json", 8)
            response = connection.getresponse()
            self.assertEqual(response.status, 408)
            self.assertIn("error", json.load(response))

    def test_hint_validates_exercise_id_and_exact_integer_level(self):
        body = {"exercise_id": "average", "code": "def average(nums):\n    return 0"}
        for changes in ({}, {"level": True}, {"level": 1.0}, {"level": "1"}, {"level": 0},
                        {"level": 4}, {"level": None}, {"level": 1, "exercise_id": "unknown"}):
            with self.subTest(changes=changes):
                status, result = self.check({**body, **changes}, "/api/hint")
                self.assertEqual(status, 400)
                self.assertIn("error", result)
        status, result = self.check({"code": body["code"], "level": 1}, "/api/hint")
        self.assertEqual(status, 400)
        self.assertIn("error", result)

    def test_hint_skips_provider_for_passed_or_invalid_code(self):
        with patch("app.get_hint") as provider:
            for code in ("def average(nums):\n    return sum(nums) / len(nums)", "def average(:"):
                with self.subTest(code=code):
                    status, result = self.check({"exercise_id": "average", "code": code, "level": 1}, "/api/hint")
                    self.assertEqual(status, 409)
                    self.assertIn("error", result)
        provider.assert_not_called()

    def test_hint_provider_receives_locally_recomputed_evidence(self):
        cloud_hint = {"hint": "核对参与平均值计算的元素数量。", "case_id": "C01",
                      "source": "agentarts", "request_id": "test-request"}
        body = {"exercise_id": "average", "code": "def average(nums):\n    return 0", "level": 2,
                "cases": [{"id": "untrusted"}], "diagnosis": "untrusted"}
        with patch("app.get_hint", return_value=cloud_hint) as provider:
            status, response = self.check(body, "/api/hint")
        self.assertEqual(status, 200)
        self.assertEqual(response, cloud_hint)
        exercise_id, result, level = provider.call_args.args
        self.assertEqual((exercise_id, level), ("average", 2))
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cases"][0]["id"], "C01")
        self.assertEqual(result["cases"][0]["actual"], 0)
        self.assertIsInstance(result["diagnosis"], dict)


if __name__ == "__main__":
    unittest.main()
