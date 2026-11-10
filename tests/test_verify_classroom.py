import unittest

from tools.verify_classroom import run


class ClassroomAcceptanceTests(unittest.TestCase):
    def test_full_local_classroom_flow_passes(self):
        report = run()
        self.assertEqual(report["failed"], 0, report)

    def test_checks_cover_roles_isolation_and_restart(self):
        names = {item["name"] for item in run()["checks"]}
        self.assertIn("跨班回复被拒绝", names)
        self.assertIn("学生不能访问教师接口", names)
        self.assertIn("求助幂等", names)
        self.assertIn("重启后记录仍在", names)


if __name__ == "__main__":
    unittest.main()