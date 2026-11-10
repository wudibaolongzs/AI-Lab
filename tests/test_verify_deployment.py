import base64
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tools.verify_deployment import run

USER, PASSWORD = "trial", "secret"


class Entry(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def authenticated(self):
        expected = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        return self.headers.get("Authorization") == expected

    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(403)
            self.end_headers()
            return
        if not self.authenticated():
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b'<title>\xe6\x99\xba\xe5\xad\xa6\xe5\xb7\xa5\xe5\x9d\x8a</title>'
                         if self.path == "/" else b'[{"id":"average"}]')

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        self.send_response(200 if self.authenticated() else 401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")


class DeploymentAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Entry)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_anonymous_rejection_and_health_isolation_pass(self):
        report = run(self.url)
        self.assertEqual(report["failed"], 0, report)
        verdicts = {item["name"]: item["verdict"] for item in report["results"]}
        self.assertEqual(verdicts["未登录访问首页"], "PASS")
        self.assertEqual(verdicts["健康检查不对外"], "PASS")
        self.assertEqual(verdicts["登录后首页"], "SKIP")

    def test_authenticated_page_and_catalog_pass(self):
        report = run(self.url, user=USER, password=PASSWORD)
        self.assertEqual(report["failed"], 0, report)
        verdicts = {item["name"]: item["verdict"] for item in report["results"]}
        self.assertEqual(verdicts["登录后首页"], "PASS")

    def test_wrong_password_is_reported_as_failure(self):
        report = run(self.url, user=USER, password="wrong")
        self.assertGreater(report["failed"], 0)

    def test_public_http_is_rejected_before_any_request(self):
        with self.assertRaises(ValueError):
            run("http://example.invalid")


if __name__ == "__main__":
    unittest.main()