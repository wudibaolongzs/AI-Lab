import unittest
from unittest.mock import patch

from agentarts import _configured_timeout


class TimeoutConfigTests(unittest.TestCase):
    def test_valid_values_are_used(self):
        self.assertEqual(_configured_timeout("15"), 15.0)
        self.assertEqual(_configured_timeout(" 2.5 "), 2.5)
        self.assertEqual(_configured_timeout("1"), 1.0)
        self.assertEqual(_configured_timeout("120"), 120.0)

    def test_invalid_values_fall_back_to_eight(self):
        for raw in ("", "abc", "0", "-1", "121", "inf", "nan"):
            with self.subTest(raw=raw):
                self.assertEqual(_configured_timeout(raw), 8.0)

    def test_environment_variable_is_read_when_no_argument_is_given(self):
        with patch.dict("os.environ", {"AI_TIMEOUT": "20"}):
            self.assertEqual(_configured_timeout(), 20.0)
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_configured_timeout(), 8.0)