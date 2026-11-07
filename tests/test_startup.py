import http.client
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from app import create_server
from tools.start import load_env


class StartupTests(unittest.TestCase):
    def test_env_is_data_and_existing_environment_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text('AGENTARTS_API_KEY="local-key"\nAGENTARTS_EXERCISES=average\n', encoding="utf-8")
            environment = {"AGENTARTS_API_KEY": "existing"}
            load_env(path, environment)
            self.assertEqual(environment, {"AGENTARTS_API_KEY": "existing", "AGENTARTS_EXERCISES": "average"})
            path.write_text("UNKNOWN=secret", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "1"):
                load_env(path, {})

    def test_external_binding_requires_explicit_host_before_opening_socket(self):
        with patch("app.ThreadingHTTPServer") as server:
            with self.assertRaises(ValueError):
                create_server(0, "0.0.0.0")
            with self.assertRaises(ValueError):
                create_server(0, "0.0.0.0", ["*"])
            server.assert_not_called()

    @unittest.skipIf(os.environ.get("AI_LAB_OFFLINE_TESTS") == "1", "offline mode: loopback HTTP tests")
    def test_explicit_host_allows_only_the_selected_authority(self):
        with create_server(0, "127.0.0.1", ["192.168.1.20"]) as server:
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for name, expected in (("192.168.1.20", 200), ("evil.example", 400)):
                    connection = http.client.HTTPConnection(*server.server_address, timeout=3)
                    connection.request("GET", "/api/exercises", headers={"Host": f"{name}:{server.server_port}"})
                    response = connection.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                    connection.close()
            finally:
                server.shutdown()
                worker.join(3)


class ProtectionStartupTests(unittest.TestCase):
    @patch("tools.start.subprocess.call", return_value=0)
    @patch("tools.start.load_env")
    def test_launcher_enables_protection_by_default(self, loader, call):
        from tools.start import main
        with patch.dict("os.environ", {}, clear=True), patch("sys.argv", ["tools/start.py"]):
            self.assertEqual(main(), 0)
        self.assertEqual(call.call_args.kwargs["env"]["AI_HINT_PROTECTION"], "1")

    @patch("tools.start.subprocess.call")
    @patch("tools.start.load_env")
    def test_invalid_protection_setting_stops_startup(self, loader, call):
        from tools.start import main
        with patch.dict("os.environ", {"AI_HINT_PROTECTION":"yes"}, clear=True):
            self.assertEqual(main(), 2)
        call.assert_not_called()
