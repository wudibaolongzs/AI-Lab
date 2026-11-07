"""Run AI-Lab's AgentArts hint branch against the local mock runtime, no cloud account needed.

For each mock mode this starts a mock runtime and an AI-Lab service wired to it, collects every
position in ``evals/samples.json`` through ``evals.run``, and checks three things a real
integration would need: the page really reports ``source == "agentarts"``, every failure mode falls
back to the local rule instead of erroring out, and the ``request_id`` / ``execution_id`` pair the
terminal logs can be matched one to one against the runtime's own execution records. The last two
rows check the exercise scope: with no switch set every exercise reaches the workflow, while an
explicit ``AGENTARTS_EXERCISES=average`` narrows the branch back to one exercise and the older
three-field payload.

    python -B tools/verify_agentarts.py

Reports: the clean run is kept as ``evals/mock-paired-results.json`` and is simulated data —
it validates wiring only, never cloud hint quality or cloud latency. Degraded-mode reports stay
in a temporary directory. Exit code is non-zero if any expectation fails.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exercise import EXERCISES, check_submission  # noqa: E402  (root is added to sys.path above)

API_KEY = "dev-mock-key"
RUNTIME_PATH = "/runtimes/ai-lab-average/invocations"
# The evaluation samples span all three exercises, so every mode states the full scope explicitly.
# The default scope and the narrowed single-exercise scope are verified separately below.
CLOUD_EXERCISES = "average,sum,count"
SAMPLE_COUNT = len(json.loads((ROOT / "evals" / "samples.json").read_text(encoding="utf-8")))
POSITIONS = 3 * SAMPLE_COUNT  # three hint levels per sample

# cloud / fallback / error out of POSITIONS positions, plus the fallback_reason the client must log.
# settle covers how long the mock lags behind a caller that hung up early.
EXPECTED = {
    "ok": {"cloud": POSITIONS, "fallback": 0, "error": 0, "reasons": set(), "settle": 0.3},
    "waiting": {"cloud": 0, "fallback": POSITIONS, "error": 0, "reasons": {"invalid_output"}, "settle": 0.3},
    "error-event": {"cloud": 0, "fallback": POSITIONS, "error": 0, "reasons": {"invalid_output"}, "settle": 0.3},
    "http-500": {"cloud": 0, "fallback": POSITIONS, "error": 0, "reasons": {"http_error"}, "settle": 0.3},
    "bad-json": {"cloud": 0, "fallback": POSITIONS, "error": 0, "reasons": {"invalid_response"}, "settle": 0.3},
    "leak-answer": {"cloud": 0, "fallback": POSITIONS, "error": 0, "reasons": {"invalid_output"}, "settle": 0.3},
    "slow": {"cloud": 0, "fallback": 3, "error": 0, "reasons": {"timeout"}, "settle": 2.5},
}
MODES = tuple(EXPECTED)


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def open_log(path):
    return open(path, "w", encoding="utf-8", errors="replace")


def wait_ready(port, path, deadline):
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}{path}", timeout=1) as response:
                if response.status == 200:
                    return True
        except (URLError, OSError):
            time.sleep(0.1)
    return False


class Stack:
    """Mock runtime plus AI-Lab service for one mode, with their terminal logs on disk."""

    def __init__(self, mode, workdir, extra_env=None, tag=None):
        self.mode = mode
        self.tag = tag or mode
        self.mock_port = free_port()
        self.app_port = free_port()
        self.mock_log = workdir / f"mock-{self.tag}.log"
        self.app_log = workdir / f"app-{self.tag}.log"
        env = dict(os.environ, AGENTARTS_WORKFLOW_URL=f"http://127.0.0.1:{self.mock_port}{RUNTIME_PATH}",
                   AGENTARTS_API_KEY=API_KEY, AGENTARTS_EXERCISES=CLOUD_EXERCISES)
        env.update(extra_env or {})
        self.app = self.mock = None
        self._mock_handle = open_log(self.mock_log)
        self._app_handle = open_log(self.app_log)
        try:
            self.mock = subprocess.Popen(
                [sys.executable, "-B", "tools/mock_agentarts.py", "--port", str(self.mock_port),
                 "--mode", mode, "--api-key", API_KEY],
                cwd=ROOT, stdout=self._mock_handle, stderr=subprocess.STDOUT)
            self.app = subprocess.Popen(
                [sys.executable, "-B", "app.py", "--port", str(self.app_port)],
                cwd=ROOT, env=env, stdout=self._app_handle, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 15
            if not wait_ready(self.mock_port, "/", deadline) or not wait_ready(self.app_port, "/api/exercises", deadline):
                raise RuntimeError("服务未能启动，请检查端口占用。")
        except BaseException:
            self.stop()
            raise

    def stop(self):
        for process in (self.app, self.mock):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
        for handle in (self._app_handle, self._mock_handle):
            handle.close()

    def records(self, path):
        records = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict):
                    records.append(parsed)
        return records

    def client_records(self):
        return [record for record in self.records(self.app_log) if "request_id" in record and "source" in record]

    def runtime_records(self):
        return [record for record in self.records(self.mock_log) if "execution_id" in record and "mode" in record]


def collect(stack, output):
    """Return the per-position outcomes for one mode, sampled like the real evaluation does."""
    if stack.mode == "slow":
        return {"attempts": 3, "cloud": 0, "fallback": _slow_fallbacks(stack), "error": 0}, None
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "evals.run", "--compare-port", str(stack.app_port),
         "--output", str(output), "--note",
         f"模拟数据：tools/mock_agentarts.py mode={stack.mode}，非真实云端调用，只验证调用链路与回退逻辑"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    if completed.returncode != 0:
        raise RuntimeError(f"evals.run 失败：{completed.stderr.strip()[-400:]}")
    report = json.loads(Path(output).read_text(encoding="utf-8"))
    summary = report["summary"]
    return {"attempts": summary["endpoint_attempts"], "cloud": summary["cloud_rows"],
            "fallback": summary["fallback_rows"], "error": summary["error_rows"]}, report


def hint_request(port, exercise_id, code, level):
    payload = json.dumps({"exercise_id": exercise_id, "code": code, "level": level}).encode("utf-8")
    request = Request(f"http://127.0.0.1:{port}/api/hint", payload, {"Content-Type": "application/json"},
                      method="POST")
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _slow_fallbacks(stack):
    code = EXERCISES["average"]["starter_code"]
    expected_first = [case["id"] for case in check_submission(code, "average")["cases"]
                      if case["status"] != "passed"][0]
    fallbacks = 0
    for _ in range(3):
        reply = hint_request(stack.app_port, "average", code, 1)
        fallbacks += reply["source"] == "local" and reply["case_id"] == expected_first
    return fallbacks


def check_scope(workdir, tag, mode_name, scope, cloud_ids, expected_reasons):
    """Probe every exercise at level 2 and verify which ones may reach the workflow."""
    started = time.monotonic()
    stack = Stack("ok", workdir, extra_env={"AGENTARTS_EXERCISES": scope}, tag=tag)
    problems, outcomes = [], {}
    try:
        for exercise_id in ("average", "sum", "count"):
            code = EXERCISES[exercise_id]["starter_code"]
            reply = hint_request(stack.app_port, exercise_id, code, 2)
            local_hint = check_submission(code, exercise_id)["hints"][1]
            want = "agentarts" if exercise_id in cloud_ids else "local"
            outcomes[exercise_id] = reply["source"]
            if reply["source"] != want:
                problems.append(f"{exercise_id} 题第 2 级提示来源是 {reply['source']}，应为 {want}")
            if want == "local" and reply["hint"] != local_hint:
                problems.append(f"{exercise_id} 题没有回到同级本地提示")
        time.sleep(0.3)
        reasons = {record.get("fallback_reason") for record in stack.client_records()
                   if record.get("source") == "local"}
        if reasons != expected_reasons:
            problems.append(f"本地回退原因是 {sorted(reasons)}，应为 {sorted(expected_reasons)}")
        calls, executions, matched, trace_problems = correlate(stack, reachers=len(cloud_ids))
        problems += trace_problems
        if matched != len(cloud_ids):
            problems.append(f"云端命中 {matched} 次，应为 {len(cloud_ids)} 次")
        seen = {record["exercise"] for record in stack.runtime_records()}
        if seen != set(cloud_ids):
            problems.append(f"运行时收到的题目是 {sorted(seen)}，应为 {sorted(cloud_ids)}")
    finally:
        stack.stop()
    cloud = sum(source == "agentarts" for source in outcomes.values())
    return {"mode": mode_name, "positions": 3, "cloud": cloud, "fallback": 3 - cloud, "error": 0,
            "reasons": "/".join(sorted(expected_reasons)) or "-", "calls": calls, "executions": executions,
            "matched": matched, "ms": round((time.monotonic() - started) * 1000), "problems": problems}


def check_default_scope(workdir):
    """With no switch set, every exercise may leave the machine."""
    return check_scope(workdir, "default", "default-scope", "", ("average", "sum", "count"), set())


def check_single_scope(workdir):
    """AGENTARTS_EXERCISES=average keeps the documented one-exercise payload and local fallback."""
    return check_scope(workdir, "single", "single-scope", "average", ("average",), {"local_exercise"})


def check_content(report):
    """Simulated cloud hints must differ from the local rule and must not hand over the answer."""
    from agentarts import _SOLUTION

    rows = [(record["sample_id"], row["level"], row["local"]["hint"], row["endpoint"])
            for record in report["records"] for row in record["levels"]]
    problems = []
    for sample_id, level, local_hint, endpoint in rows:
        if endpoint["outcome"] != "cloud":
            continue
        hint = endpoint["hint"]
        if hint == local_hint:
            problems.append(f"{sample_id}/L{level} 与本地提示完全相同，疑似未走云端分支")
        if _SOLUTION.search(hint):
            problems.append(f"{sample_id}/L{level} 泄露了答案代码")
        if len(hint.splitlines()) != 1 or not 0 < len(hint.strip()) <= 240:
            problems.append(f"{sample_id}/L{level} 提示格式不符合约定")
    return len(rows), problems


def correlate(stack, reachers=None):
    """Every logged AgentArts call must be traceable to one runtime execution record.

    ``reachers`` is how many client calls should have arrived at the runtime. Every mock mode
    answers a call it received, so the default is all of them; the default-scope row passes 1.
    """
    clients = stack.client_records()
    reachers = len(clients) if reachers is None else reachers
    runtimes = {record["execution_id"]: record for record in stack.runtime_records()}
    problems = []
    matched = 0
    for record in clients:
        if record.get("source") != "agentarts":
            continue
        execution = record.get("execution_id")
        runtime = runtimes.get(execution)
        if runtime is None:
            problems.append(f"终端日志里的 execution_id {execution} 在运行记录中找不到")
        elif runtime["request_id"] != record["request_id"]:
            problems.append(f"{execution} 的请求编号与终端日志不一致")
        else:
            matched += 1
    if len(runtimes) < reachers:
        problems.append(f"运行记录 {len(runtimes)} 条少于应有 {reachers} 条（客户端日志 {len(clients)} 条）")
    return len(clients), len(runtimes), matched, problems


def run_mode(mode, workdir):
    want = EXPECTED[mode]
    stack = Stack(mode, workdir)
    try:
        output = ROOT / "evals" / "mock-paired-results.json" if mode == "ok" else workdir / f"report-{mode}.json"
        started = time.monotonic()
        counts, report = collect(stack, output)
        time.sleep(want["settle"])  # let both processes finish writing their log lines
        calls, executions, matched, problems = correlate(stack)
        if report is not None:
            positions, content_problems = check_content(report)
            problems += content_problems
        else:
            positions = counts["attempts"]
        reasons = {record.get("fallback_reason") for record in stack.client_records()
                   if record.get("source") == "local"}
    finally:
        stack.stop()
    if reasons != want["reasons"]:
        problems.append(f"回退原因 {sorted(reasons)} 与预期 {sorted(want['reasons'])} 不符")
    got = (counts["cloud"], counts["fallback"], counts["error"])
    if got != (want["cloud"], want["fallback"], want["error"]):
        problems.append(f"云端 {counts['cloud']}/{want['cloud']}，回退 {counts['fallback']}/{want['fallback']}，"
                        f"错误 {counts['error']}/{want['error']}")
    return {
        "mode": mode, "positions": positions, "cloud": counts["cloud"], "fallback": counts["fallback"],
        "error": counts["error"], "reasons": "/".join(sorted(reasons)) or "-", "calls": calls,
        "executions": executions, "matched": matched, "ms": round((time.monotonic() - started) * 1000),
        "problems": problems,
    }


def main():
    if sys.version_info < (3, 9):
        sys.exit("需要 Python 3.9 或更新版本。")
    workdir = Path(tempfile.mkdtemp(prefix="ai-lab-mock-"))
    results = []
    try:
        for mode in MODES:
            try:
                results.append(run_mode(mode, workdir))
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
                results.append({"mode": mode, "problems": [f"{type(error).__name__}: {error}"]})
        for check in (check_default_scope, check_single_scope):
            try:
                results.append(check(workdir))
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as error:
                name = "default-scope" if check is check_default_scope else "single-scope"
                results.append({"mode": name, "problems": [f"{type(error).__name__}: {error}"]})
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print(f"{'mode':<14}{'pos':>5}{'cloud':>7}{'local':>7}{'err':>5}{'fallback_reason':>18}"
          f"{'logged/calls/execs/matched':>28}{'ms':>9}")
    print("-" * 94)
    for row in results:
        if "cloud" not in row:
            print(f"{row['mode']:<14}  未完成：{row['problems'][0]}")
            continue
        trace = f"{row['calls']}/{row['matched']}/{row['executions']}"
        print(f"{row['mode']:<14}{row['positions']:>5}{row['cloud']:>7}{row['fallback']:>7}{row['error']:>5}"
              f"{row['reasons']:>18}{trace:>28}{row['ms']:>9}")
        for problem in row["problems"]:
            print(f"{'':<14}! {problem}")
    failed = [row for row in results if row.get("problems")]
    print("-" * 94)
    verdict = "全部通过：AgentArts 分支与各回退路径在本机可用。" if not failed else "存在未通过项，请先修复再联调。"
    print(f"{len(results) - len(failed)}/{len(results)} 项检查通过。{verdict}")
    print("说明：以上为模拟运行数据，验证的是调用链路与回退逻辑，不代表真实云端的提示质量与耗时。")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
