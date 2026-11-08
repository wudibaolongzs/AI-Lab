import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch
from app import create_server

@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
class LearningHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(0)
        cls.worker = threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join(3)
        cls.server.server_close()
    def request(self,method,path,payload=None):
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        connection.request(method,path,None if payload is None else json.dumps(payload),{"Content-Type":"application/json"})
        response=connection.getresponse()
        data=response.read()
        connection.close()
        return response.status,json.loads(data)
    def test_challenge_is_public_but_does_not_expose_answer(self):
        status,data=self.request("GET","/api/learning/challenge?exercise_id=average")
        self.assertEqual(status,200)
        self.assertIn("question",data)
        self.assertNotIn("answer",data)
        self.assertNotIn("expected",data)
    def test_challenge_rejects_unknown_or_duplicate_id(self):
        for query in ("exercise_id=missing","exercise_id=average&exercise_id=sum",""):
            self.assertEqual(self.request("GET","/api/learning/challenge?"+query)[0],400)
    def test_verification_requires_original_pass(self):
        payload={"exercise_id":"average","code":"def average(nums):\n    return 0","answer":0}
        self.assertEqual(self.request("POST","/api/learning/verify",payload)[0],409)
    def test_classroom_disabled_is_unavailable(self):
        with patch.dict("os.environ",{"AI_CLASSROOM_CONFIG":""}):
            self.assertEqual(self.request("GET","/api/classroom/student")[0],503)
