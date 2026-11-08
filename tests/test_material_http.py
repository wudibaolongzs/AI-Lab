import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
import app

class MaterialHTTPTests(unittest.TestCase):
    def handler(self,path,body=b"{}"):
        h=object.__new__(app.Handler)
        h.path=path; h.command="POST"; h.headers=Message()
        h.headers["Content-Type"]="application/json"
        h.headers["Content-Length"]=str(len(body)); h.rfile=io.BytesIO(body)
        h.is_local_host=lambda:True
        h.reject=lambda status,message:setattr(h,"result",(status,message))
        h.send_json=lambda status,data:setattr(h,"result",(status,data))
        h.drain_body=lambda count:None
        return h
    def test_material_route_dispatch_and_own_large_body_limit(self):
        h=self.handler("/api/materials/text",json.dumps({"text":"x"*20000}).encode())
        with patch("app.teacher_materials.dispatch",side_effect=lambda handler,payload:handler.send_json(200,payload)):
            h.do_POST()
        self.assertEqual(h.result[0],200)
        self.assertEqual(len(h.result[1]["text"]),20000)
    def test_original_check_limit_is_unchanged(self):
        h=self.handler("/api/check",json.dumps({"code":"x"*20000}).encode())
        h.do_POST(); self.assertEqual(h.result[0],413)
    def test_material_over_limit_rejected(self):
        h=self.handler("/api/materials/ocr",b"x"*(4*1024*1024+1))
        h.do_POST(); self.assertEqual(h.result[0],413)
