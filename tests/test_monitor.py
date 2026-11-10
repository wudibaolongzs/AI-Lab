import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.monitor import summarise, load, main


def row(source, elapsed, reason=None, minutes_ago=0):
    stamp = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return {"ts": stamp.isoformat(timespec="seconds"), "request_id": "r",
            "source": source, "elapsed_ms": elapsed, "fallback_reason": reason}


class MonitorTests(unittest.TestCase):
    def test_cloud_and_fallback_rates_are_counted_separately(self):
        report = summarise([row("agentarts", 12000), row("agentarts", 8000),
                            row("local", 500, "timeout"), row("local", 400, "http_error")])
        self.assertEqual(report["calls"], 4)
        self.assertEqual(report["cloud_calls"], 2)
        self.assertEqual(report["fallback_calls"], 2)
        self.assertEqual(report["cloud_rate"], 0.5)
        self.assertEqual(report["fallback_reasons"]["timeout"], 1)
        self.assertEqual(report["latency_cloud"]["max_ms"], 12000)

    def test_time_window_skips_old_and_undated_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.jsonl"
            lines = [row("agentarts", 1000), row("agentarts", 2000, minutes_ago=90),
                     {"source": "local", "elapsed_ms": 1}]
            path.write_text("\n".join(json.dumps(item) for item in lines), encoding="utf-8")
            rows, undated = load([path], since_minutes=30)
        self.assertEqual(len(rows), 1)
        self.assertEqual(undated, 1)

    def test_budget_breach_makes_the_command_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "app.jsonl"
            path.write_text("\n".join(json.dumps(row("agentarts", 100)) for _ in range(3)), encoding="utf-8")
            self.assertEqual(main([str(path), "--budget-per-day", "2"]), 1)
            self.assertEqual(main([str(path), "--budget-per-day", "3"]), 0)

    def test_missing_log_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.jsonl"
            path.write_text("not json\n", encoding="utf-8")
            self.assertEqual(main([str(path)]), 2)


if __name__ == "__main__":
    unittest.main()