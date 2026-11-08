import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch
from app import create_server

@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS")=="1","offline mode: loopback HTTP tests")
class RemoteHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=create_server(0)
        cls.worker=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.worker.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.worker.join(3);cls.server.server_close()
    def request(self,method,path,body=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        c.request(method,path,None if body is None else json.dumps(body),{"Content-Type":"application/json"})
        r=c.getresponse();data=json.loads(r.read());c.close();return r.status,data
    def test_public_config_never_contains_token(self):
        with patch.dict("os.environ",{"LUOGU_ENABLED":"0","LUOGU_OPENAPP_TOKEN":"private-secret"}):
            status,data=self.request("GET","/api/remote/config")
        self.assertEqual(status,200);self.assertFalse(data["enabled"])
        self.assertNotIn("private-secret",json.dumps(data))
    def test_remote_cannot_use_local_check_or_hint(self):
        import question_bank
        item=next(p for p in question_bank.public_exercises() if p["engine"]=="luogu_remote")
        for path in ("/api/check","/api/hint"):
            status,_=self.request("POST",path,{"exercise_id":item["id"],"code":"print(1)","level":1})
            self.assertEqual(status,409)
    def test_catalog_remote_filter(self):
        status,data=self.request("GET","/api/catalog?mode=remote&page_size=100")
        self.assertEqual(status,200);self.assertEqual(data["total"],300)
        self.assertEqual(len(data["items"]),100)
