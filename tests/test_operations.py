import http.client
import json
import os
import socket
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from app import create_server


class DeploymentTemplateTests(unittest.TestCase):
    def test_gateway_covers_page_and_api_and_clears_identity(self):
        root = Path(__file__).resolve().parents[1]
        nginx = (root / "deploy/nginx.conf").read_text()
        protected = nginx.split("location / {", 1)[1]
        self.assertIn('auth_basic_user_file /etc/ict-trial/htpasswd;', protected)
        self.assertIn('proxy_set_header Host 127.0.0.1:8000;', protected)
        self.assertIn('proxy_set_header Authorization "";', protected)
        self.assertIn('proxy_set_header X-Forwarded-User "";', protected)
        health = nginx.split('location = /healthz {', 1)[1].split('}', 1)[0]
        self.assertIn('deny all;', health)
        self.assertIn('allow 127.0.0.1;', health)
        service = (root / "deploy/ict-trial.service").read_text()
        self.assertIn('User=ict-trial', service)
        self.assertIn('EnvironmentFile=/etc/ict-trial/environment', service)
        self.assertIn('--host 127.0.0.1 --port 8000', service)


@unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.server = create_server(0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(thread.join, 5)
        self.addCleanup(self.server.shutdown)

    def request(self, path, host=None):
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        self.addCleanup(conn.close)
        conn.request("GET", path, headers={"Host": host} if host else {})
        response = conn.getresponse()
        return response.status, response.read()

    def test_health_never_calls_provider(self):
        with patch("app.get_hint", side_effect=AssertionError("provider called")):
            status, body = self.request("/healthz")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {"status": "ok"})

    def test_health_retains_host_boundary(self):
        self.assertEqual(self.request("/healthz", "attacker.invalid")[0], 400)

    def test_access_log_omits_unknown_path_and_query_secrets(self):
        with self.assertLogs("ict.access", level="INFO") as logs:
            self.request("/secret-token?key=private")
        data = json.loads(logs.records[0].getMessage())
        self.assertEqual(data, {"event": "access", "method": "GET", "route": "unknown", "status": 404})
        self.assertNotIn("private", str(logs.output))

    def test_overload_returns_503_without_spawning_worker(self):
        for _ in range(16):
            self.assertTrue(self.server.worker_slots.acquire(blocking=False))
        try:
            conn = socket.create_connection(self.server.server_address, timeout=2)
            self.addCleanup(conn.close)
            self.assertTrue(conn.recv(1024).startswith(b"HTTP/1.1 503"))
        finally:
            for _ in range(16):
                self.server.worker_slots.release()
        self.assertEqual(self.request("/healthz")[0], 200)
