"""End-to-end acceptance for the optional classroom workbench on this machine.

Creates temporary credentials outside the repository, starts the real app
server in-process, and proves role isolation, cross-class isolation,
idempotency and restart persistence. It never prints a token.
"""

import argparse
import http.client
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_server
from exercise import EXERCISES


def request(server, method, path, token=None, payload=None, timeout=10):
    host, port = server.server_address[0], server.server_address[1]
    connection = http.client.HTTPConnection(host, port, timeout=timeout)
    headers = {}
    body = None
    if token:
        headers["X-Classroom-Token"] = token
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read(65536)
        status = response.status
    finally:
        connection.close()
    try:
        parsed = json.loads(raw) if raw else None
    except ValueError:
        parsed = None
    return status, parsed


def check(checks, name, ok, detail):
    checks.append({"name": name, "verdict": "PASS" if ok else "FAIL", "detail": detail})


def run():
    checks = []
    directory = tempfile.TemporaryDirectory()
    config_path = Path(directory.name) / "credentials.json"
    database = Path(directory.name) / "classroom.sqlite"
    tokens = {
        "class-a": {"teacher": "teacher-a-" + "x" * 24,
                    "students": {"student-01": "student-one-" + "x" * 24,
                                 "student-02": "student-two-" + "x" * 24}},
        "class-b": {"teacher": "teacher-b-" + "y" * 24,
                    "students": {"student-03": "student-three-" + "y" * 24}},
    }
    config_path.write_text(json.dumps({"classes": {
        class_id: {"teacher_token": values["teacher"], "students": values["students"]}
        for class_id, values in tokens.items()
    }}, ensure_ascii=False), encoding="utf-8")
    previous = {key: os.environ.get(key) for key in ("AI_CLASSROOM_CONFIG", "AI_CLASSROOM_DB")}
    os.environ["AI_CLASSROOM_CONFIG"] = str(config_path)
    os.environ["AI_CLASSROOM_DB"] = str(database)
    servers = []

    def start():
        server = create_server(0, "127.0.0.1")
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return server

    try:
        server = start()
        teacher_a = tokens["class-a"]["teacher"]
        student_a = tokens["class-a"]["students"]["student-01"]
        student_b = tokens["class-a"]["students"]["student-02"]
        teacher_b = tokens["class-b"]["teacher"]

        status, data = request(server, "GET", "/api/classroom/student", student_a)
        check(checks, "学生初始可读", status == 200 and data["tasks"] == [], f"HTTP {status}")

        status, task = request(server, "POST", "/api/classroom/tasks", teacher_a,
                               {"exercise_id": "average", "title": "平均值练习", "due": "本周五"})
        check(checks, "教师发布任务", status == 200 and isinstance(task.get("id"), str), f"HTTP {status}")

        status, data = request(server, "GET", "/api/classroom/student", student_a)
        check(checks, "学生收到任务", status == 200 and len(data["tasks"]) == 1, f"HTTP {status}")

        status, help_record = request(server, "POST", "/api/classroom/help", student_a, {
            "exercise_id": "average", "submission_id": "sub-1", "request_id": "req-1",
            "question": "为什么分母要用元素个数？", "source": "manual"})
        check(checks, "学生提交求助", status == 200 and isinstance(help_record.get("id"), str), f"HTTP {status}")

        status, again = request(server, "POST", "/api/classroom/help", student_a, {
            "exercise_id": "average", "submission_id": "sub-1", "request_id": "req-1",
            "question": "重复提交不应新增", "source": "manual"})
        check(checks, "求助幂等", status == 200 and again.get("id") == help_record.get("id"), f"HTTP {status}")

        status, other_student = request(server, "GET", "/api/classroom/student", student_b)
        check(checks, "同班学生互不可见", status == 200 and other_student["help"] == [], f"HTTP {status}")

        status, queue = request(server, "GET", "/api/classroom/teacher", teacher_a)
        counts = queue.get("counts") if isinstance(queue, dict) else {}
        check(checks, "教师看到待回复", status == 200 and counts.get("help_requests") == 1
              and counts.get("unanswered") == 1, f"HTTP {status}")

        status, _ = request(server, "POST", "/api/classroom/reply", teacher_b,
                            {"help_id": (help_record or {}).get("id") or "missing", "reply": "跨班回复应失败"})
        check(checks, "跨班回复被拒绝", status == 404, f"HTTP {status}（期望 404）")

        status, _ = request(server, "GET", "/api/classroom/teacher", student_a)
        check(checks, "学生不能访问教师接口", status == 403, f"HTTP {status}（期望 403）")

        status, _ = request(server, "GET", "/api/classroom/student", "invalid-token")
        check(checks, "无效凭证被拒绝", status == 401, f"HTTP {status}（期望 401）")

        status, _ = request(server, "POST", "/api/classroom/reply", teacher_a,
                            {"help_id": (help_record or {}).get("id") or "missing", "reply": "先看分母是不是元素个数。"})
        check(checks, "教师回复本班求助", status == 200, f"HTTP {status}")

        status, data = request(server, "GET", "/api/classroom/student", student_a)
        reply = data["help"][0].get("reply") if status == 200 and data["help"] else None
        check(checks, "学生看到回复", reply == "先看分母是不是元素个数。", f"HTTP {status}")

        closed = servers.pop()
        closed.shutdown()
        closed.server_close()
        server = start()
        status, queue = request(server, "GET", "/api/classroom/teacher", teacher_a)
        persisted = status == 200 and queue["counts"]["help_requests"] == 1 and queue["help"][0].get("reply")
        check(checks, "重启后记录仍在", bool(persisted), f"HTTP {status}")
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        directory.cleanup()

    report = {
        "kind": "classroom_acceptance",
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "checks": checks,
    }
    report["failed"] = sum(item["verdict"] == "FAIL" for item in checks)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="本机课堂工作台端到端验收")
    parser.add_argument("--json", type=Path, help="写出报告文件")
    args = parser.parse_args(argv)
    report = run()
    for item in report["checks"]:
        print(f"[{item['verdict']:<4}] {item['name']}：{item['detail']}")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果：{report['failed']} 项失败。真实班级试用仍需操作员凭据与真人参与。")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())