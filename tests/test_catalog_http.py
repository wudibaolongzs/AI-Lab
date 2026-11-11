import http.client
import json
import os
import threading
import unittest
from app import create_server

@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
class CatalogHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=create_server(0)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.thread.join(3);cls.server.server_close()
    def get(self,path):
        client=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        client.request("GET",path)
        response=client.getresponse();value=json.loads(response.read());client.close()
        return response.status,value
    def test_public_pages_never_expose_private_material(self):
        status,page=self.get("/api/catalog?mode=local&page=1&page_size=12")
        self.assertEqual(status,200);self.assertEqual(page["total"],28)
        self.assertEqual(len(page["items"]),12)
        for item in page["items"]:
            for key in ("cases","reference_code","transfer","legacy_guidance","hints"):
                self.assertNotIn(key,item)
            status,detail=self.get("/api/problems/"+item["id"])
            self.assertEqual(status,200);self.assertEqual(detail,item)
    def test_catalog_parameters_rejected_and_empty_search_supported(self):
        for query in ("page=0","page=-1","page=abc","page_size=0","page_size=100000","page=1&page=2"):
            self.assertEqual(self.get("/api/catalog?"+query)[0],400)
        status,page=self.get("/api/catalog?query=not-a-real-problem")
        self.assertEqual(status,200);self.assertEqual(page["items"],[])
    def test_catalog_options_cover_reference_bank(self):
        status,options=self.get("/api/catalog/options")
        self.assertEqual(status,200)
        for tag in ("二进制","前缀"):
            self.assertIn(tag,options["tags"])
        self.assertIn("本地导入题库",options["sources"])
        self.assertEqual(options["languages"],["python","cpp"])
        from urllib.parse import urlencode
        status,page=self.get("/api/catalog?"+urlencode({"mode":"reference","tag":"前缀","language":"cpp","page":1,"page_size":12}))
        self.assertEqual(status,200);self.assertGreater(page["total"],0)
        for item in page["items"]:
            self.assertIn("前缀",item["tags"]);self.assertEqual(item["language"],"cpp")
    def test_non_transfer_problem_is_explicit(self):
        import question_bank
        problem=next(p for p in question_bank.public_exercises() if not p["has_transfer"])
        status,data=self.get("/api/learning/challenge?exercise_id="+problem["id"])
        self.assertEqual(status,200);self.assertFalse(data["available"])
