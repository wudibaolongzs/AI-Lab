import base64
import os
import unittest
from unittest.mock import patch
import baidu_ocr

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x"*20).decode()

class BaiduTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"BAIDU_OCR_ENABLED":"1", "BAIDU_OCR_API_KEY":"key", "BAIDU_OCR_SECRET_KEY":"secret"})
        self.env.start(); self.addCleanup(self.env.stop)
        baidu_ocr._cache.clear()
    def test_disabled_never_sends(self):
        with patch.dict(os.environ, {"BAIDU_OCR_ENABLED":"0"}), patch.object(baidu_ocr, "_post") as send:
            with self.assertRaises(baidu_ocr.OCRError) as e: baidu_ocr.recognize(PNG)
            self.assertEqual(e.exception.status,503); send.assert_not_called()
    def test_invalid_image_never_sends(self):
        for image in ["https://bad.test/img", "abcd", "", "!bad", base64.b64encode(b"x"*(2*1024*1024+1)).decode()]:
            with self.subTest(image=image[:20]), patch.object(baidu_ocr,"_post") as send:
                with self.assertRaises(baidu_ocr.OCRError): baidu_ocr.recognize(image)
                send.assert_not_called()
    def test_oauth_cached_and_lines_returned(self):
        with patch.object(baidu_ocr,"_post", side_effect=[{"access_token":"access", "expires_in":3600}, {"log_id":123,"words_result":[{"words":"first"},{"words":"second"}]}, {"words_result":[{"words":"next"}]}]) as send:
            self.assertEqual(baidu_ocr.recognize(PNG), {"text":"first\nsecond", "log_id":"123"})
            self.assertEqual(baidu_ocr.recognize(PNG)["text"],"next")
            self.assertEqual(send.call_count,3)
            self.assertIn("oauth/2.0/token",send.call_args_list[0].args[0])
            self.assertIn("accurate_basic",send.call_args_list[1].args[0])
    def test_errors_do_not_leak_provider_secrets(self):
        for response in [{"error":"secret"},{"error_code":110,"error_msg":"secret"},{"words_result":[]},{"words_result":[{"words":"x"*20001}]}]:
            with self.subTest(response=str(response)[:30]), patch.object(baidu_ocr,"_post", side_effect=[{"access_token":"access","expires_in":3600},response]):
                baidu_ocr._cache.clear()
                with self.assertRaises(baidu_ocr.OCRError) as e: baidu_ocr.recognize(PNG)
                self.assertNotIn("secret",str(e.exception))
    def test_no_redirect(self):
        self.assertIsNone(baidu_ocr.NoRedirect().redirect_request(None,None,302,"",{},"https://evil.test"))
