"""Stand in for a published AgentArts workflow until cloud credentials exist.

The server speaks the documented runtime contract — ``POST /runtimes/{name}/invocations``,
``Authorization: Bearer <api key>``, a ``text/event-stream`` reply and a final
``workflow_finished`` event carrying ``data.status`` plus ``data.outputs.user_fields`` —
so AI-Lab's AgentArts branch and every fallback path can be verified on one machine.

The hint text is scripted from the evidence, not model generated. This harness proves the
wiring, the output validation and the fallback behaviour; it says nothing about real
cloud hint quality or cloud latency. Keep its reports separate from paired cloud runs.

Usage (PowerShell, from the AI-Lab directory):

    python -B tools/mock_agentarts.py --port 8931 --mode ok
    $env:AGENTARTS_WORKFLOW_URL = "http://127.0.0.1:8931/runtimes/ai-lab-average/invocations"
    $env:AGENTARTS_API_KEY = "dev-mock-key"
    python -B app.py --port 8001

Modes: ok, waiting, error-event, http-500, bad-json, leak-answer, slow.
"""

import argparse
import json
import re
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

INVOCATION_PATH = re.compile(r"^/runtimes/[A-Za-z0-9][A-Za-z0-9._-]{0,63}/invocations$")
MAX_BODY_BYTES = 64 * 1024
DRAIN_CEILING = 4 * 1024 * 1024  # read at most this much so an oversized caller cannot stall a worker
MAX_HINT_LENGTH = 240
MODES = ("ok", "waiting", "error-event", "http-500", "bad-json", "leak-answer", "slow")
ANSWER_LEAK = "把 return 改成 sum(nums) / len(nums) 就对了。"
_API_KEY_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _render(value):
    return json.dumps(value, ensure_ascii=False, separators=(", ", ": "))


def _at(line):
    return f"第 {line} 行" if isinstance(line, int) else "返回那一步"


def _exercise_kind(title, exercise_id):
    """Pick the wording family from the workflow input, the same way the diagnostic node would."""
    if exercise_id in ("average", "sum", "count"):
        return exercise_id
    if "总和" in title:
        return "sum"
    if "个数" in title or "计数" in title:
        return "count"
    if "平均" in title:
        return "average"
    return "generic"


SYNTAX_HINTS = (
    "Python 对函数头的冒号、函数体的缩进和最后一行的返回值各有什么写法要求？",
    "诊断落在{at}：{message} 核对该行与上一行的括号、冒号和缩进。",
    "把{at}之前的步骤先删到最少，让测试能跑起来，再逐步加回计算。",
)
# Scripted stand-in for the workflow's teaching node: one triple per exercise and diagnosis
# kind. A sum hint must not borrow the average exercise's denominator and a count hint must
# not borrow its value total, otherwise the scripted cloud text is worse than the local rule.
SCRIPTED_HINTS = {
    "average": {
        "zero_division": (
            "输入只有 {size} 个元素时，除数应该等于几？先想清楚这个分母代表什么。",
            "用例 {case_id} 的输入是 {listed}，共 {size} 个元素。检查{at}的除数怎样变成了 0。",
            "把 {size} 代进{at}的除数，看它是否随元素个数变化，再用用例 {case_id} 复测。",
        ),
        "numeric_range": (
            "{listed} 里最小和最大的数各是多少？平均值会落在它们之外吗？",
            "{actual_clause}。检查{at}哪一步把数值放大了。",
            "分别手算这 {size} 个元素的总和与个数，再核对{at}用到的两个量。",
        ),
        "wrong_result": (
            "用例 {case_id} 的输入是 {listed}，期望 {expected}，实际 {actual}。平均值是拿哪两个量相除得到的？",
            "{size} 个元素期望得到 {expected}，实际却是 {actual}。检查{at}相除时用的分母。",
            "手算 {listed} 的总和与元素个数 {size}，用这两个量复算用例 {case_id}，再对照代码。",
        ),
    },
    "sum": {
        "zero_division": (
            "这道题只要把元素相加，{at}为什么会走到除法？",
            "用例 {case_id} 的输入是 {listed}，共 {size} 个元素。检查{at}的除数怎样变成了 0。",
            "去掉除法，手算 {listed} 的相加结果，再用用例 {case_id} 复测。",
        ),
        "numeric_range": (
            "{listed} 里最小和最大的数各是多少？这组数相加最多能到多少？",
            "{actual_clause}。检查{at}哪一步把数值放大了。",
            "手算 {listed} 的相加结果，看你的式子算出的结果比它大了多少倍，再回到相加那一步。",
        ),
        "wrong_result": (
            "用例 {case_id} 的输入是 {listed}，期望 {expected}，实际 {actual}。这个列表的相加结果应该是多少，实际值更像它还是更像元素个数 {size}？",
            "{size} 个元素期望得到 {expected}，实际却是 {actual}。检查{at}把哪个量当成了结果。",
            "手算 {listed} 的相加结果，再数出元素个数 {size}，对照{at}确认用的是前者。",
        ),
    },
    "count": {
        "zero_division": (
            "这道题只要数出有几个位置，{at}为什么会走到除法？",
            "用例 {case_id} 的输入是 {listed}，共 {size} 个元素。检查{at}的除数怎样变成了 0。",
            "去掉除法，直接数 {listed} 占几个位置，再用用例 {case_id} 复测。",
        ),
        "numeric_range": (
            "{listed} 一共占几个位置？返回值为什么会远大于这个数？",
            "{actual_clause}。检查{at}把什么当成了个数。",
            "按位置数出 {size} 个元素，对照{at}的返回值，只保留计数那一步。",
        ),
        "wrong_result": (
            "用例 {case_id} 的输入是 {listed}，期望 {expected}，实际 {actual}。这组输入占 {size} 个位置，它们的相加结果又是多少，实际值更像哪一个？",
            "{listed} 里 0 和重复的值各占几个位置？检查{at}数的是位置还是数值。",
            "按位置给 {listed} 编号并数出 {size} 个位置，再用例 {case_id} 对照{at}的结果。",
        ),
    },
    "generic": {
        "wrong_result": (
            "用例 {case_id} 的输入是 {listed}，期望 {expected}，实际 {actual}。期望值是由哪些量算出来的？",
            "{size} 个元素期望得到 {expected}，实际却是 {actual}。检查{at}参与计算的各个量。",
            "手算 {listed} 的期望结果，再对照{at}用到的量复算用例 {case_id}。",
        ),
    },
}


def build_hint(level, case, diagnosis, exercise="average"):
    """Script one evidence-based hint, level 1 asks, 2 locates, 3 gives a next step."""
    kind = diagnosis.get("kind") if isinstance(diagnosis, dict) else None
    line = diagnosis.get("line") if isinstance(diagnosis, dict) else None
    message = str(diagnosis.get("message", ""))[:60] if isinstance(diagnosis, dict) else ""
    case_id = case.get("id", "C01")
    nums = case.get("input")
    size = len(nums) if isinstance(nums, list) else None
    listed = _render(nums) if isinstance(nums, list) else "这组输入"
    fields = {"case_id": case_id, "listed": listed, "size": size, "expected": case.get("expected"),
              "actual": case.get("actual"), "at": _at(line), "message": message}
    # A case that raised has no actual value to quote; say what happened instead of printing None.
    fields["actual_clause"] = (f"用例 {case_id} 实际得到 {fields['actual']}，超出了预期范围"
                               if fields["actual"] is not None
                               else f"用例 {case_id} 的返回值超出了本题支持的数值范围")

    if kind in ("syntax", "unsupported"):
        templates = SYNTAX_HINTS  # formatting advice is the same for every exercise
    else:
        family = SCRIPTED_HINTS.get(exercise) or SCRIPTED_HINTS["average"]
        # Fall back to the average wording only for a diagnosis this exercise never sees.
        templates = family.get(kind) or SCRIPTED_HINTS["average"].get(kind) or family["wrong_result"]
    hint = templates[level - 1].format(**fields)
    if len(hint) > MAX_HINT_LENGTH:
        raise ValueError(f"脚本提示超过 {MAX_HINT_LENGTH} 字，客户端会拒绝：{hint}")
    return hint


def _validate(payload):
    """Mirror the start node's required inputs and return the call's evidence."""
    if not isinstance(payload, dict) or not isinstance(payload.get("inputs"), dict):
        raise ValueError("请提供 inputs 对象。")
    inputs = payload["inputs"]
    title = inputs.get("exercise_title")
    level = inputs.get("hint_level")
    raw_evidence = inputs.get("evidence_json")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("exercise_title 必须是非空字符串。")
    if type(level) is not int or not 1 <= level <= 3:
        raise ValueError("hint_level 必须是 1 到 3 的整数。")
    if not isinstance(raw_evidence, str):
        raise ValueError("evidence_json 必须是字符串。")
    raw_exercise = inputs.get("exercise_id")
    if raw_exercise is not None and not isinstance(raw_exercise, str):
        raise ValueError("exercise_id 需要是字符串。")
    evidence = json.loads(raw_evidence)
    if not isinstance(evidence, dict) or not isinstance(evidence.get("cases"), list) or not evidence["cases"]:
        raise ValueError("evidence_json 需要含至少一个用例的 cases 数组。")
    case = evidence["cases"][0]
    if not isinstance(case, dict) or not isinstance(case.get("id"), str):
        raise ValueError("cases 中的用例需要带 id。")
    diagnosis = evidence.get("diagnosis")
    if not isinstance(diagnosis, dict):
        raise ValueError("evidence_json 需要带 diagnosis 对象。")
    return title, level, case, diagnosis, _exercise_kind(title, raw_exercise)


def build_events(mode, execution_id, case_id, summary, hint):
    """The SSE events one execution replays, in the order the runtime publishes them."""
    events = [
        {"event": "workflow_started", "data": {"execution_id": execution_id, "status": "running"}},
        {"event": "node_started", "data": {"node_id": "diagnose", "node_type": "llm"}},
        {"event": "node_finished", "data": {
            "node_id": "diagnose", "status": {"code": 1, "desc": "succeeded"},
            "outputs": {"user_fields": {"diagnostic_summary": summary, "case_id": case_id}}}},
        {"event": "message", "data": {"text": "正在整理证据。", "is_finished": False}},
    ]
    if mode == "error-event":
        events.append({"event": "error", "data": {
            "code": 500, "error_code": "MOCK_ERROR", "message": "模拟节点执行失败。"}})
        return events
    if mode == "waiting":
        status, fields = {"code": 2, "desc": "waiting"}, {}
    else:
        status = {"code": 1, "desc": "succeeded"}
        fields = {"hint": ANSWER_LEAK if mode == "leak-answer" else hint, "case_id": case_id}
    events.append({"event": "workflow_finished", "data": {
        "status": status, "execution_id": execution_id,
        "outputs": {"responseContent": summary, "user_fields": fields}}})
    return events


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentArtsMock/1"
    sys_version = ""
    timeout = 5  # a caller that declares a body and never writes it must not wedge a worker thread

    def log_message(self, format, *args):
        pass  # Access logs would bury the one-line JSON records the harness correlates.

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_event(self, event):
        self.wfile.write(f"data: {json.dumps(event, ensure_ascii=False)}\r\n\r\n".encode("utf-8"))

    def stream_open(self):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.flush()

    def read_declared_body(self):
        """Read the declared body before any reply: answering with bytes still in flight can lose the answer.

        Windows can reset the connection when the server closes while the client is still writing,
        which would show up as a client-side connection_error instead of the intended status code.
        """
        declared = self.headers.get("Content-Length", "")
        if declared.isascii() and declared.isdigit() and len(declared) <= len(str(DRAIN_CEILING)):
            remaining = min(int(declared), DRAIN_CEILING)
        else:
            remaining = 0 if not declared.isdigit() else DRAIN_CEILING  # an absurd length still cannot stall us
        chunks = []
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(8192, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        except OSError:  # timed out, or the client disconnected mid-body: answer with what arrived
            pass
        return b"".join(chunks)

    def do_POST(self):
        body = self.read_declared_body()
        if not INVOCATION_PATH.fullmatch(self.path):
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "调用路径应为 /runtimes/{名称}/invocations。"})
            return
        expected = f"Bearer {self.server.api_key}"
        if self.headers.get("Authorization", "") != expected:
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "API Key 校验失败。"})
            return
        if self.headers.get_content_type() != "application/json":
            self.send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "请提交 JSON。"})
            return
        if len(body) > MAX_BODY_BYTES:
            self.send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "请求体过大。"})
            return
        try:
            call = _validate(json.loads(body.decode("utf-8")))
        except (ValueError, KeyError, AttributeError, RecursionError, UnicodeDecodeError) as error:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": f"输入不符合开始节点的约定：{error}"})
            return
        self.server.deliver(self, call)

    def do_GET(self):
        self.send_json(HTTPStatus.OK, {"mode": self.server.mode, "modes": list(MODES)})


class MockServer(ThreadingHTTPServer):
    """Threaded loopback server that replays one AgentArts workflow execution per request."""

    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, mode="ok", api_key="dev-mock-key", slow_seconds=9.0, log=None):
        super().__init__(address, Handler)
        self.mode = mode
        self.api_key = api_key
        self.slow_seconds = slow_seconds
        self.sequence = 0
        self.sink = log or self._print_record

    def new_execution_id(self):
        self.sequence += 1
        return f"mock-exec-{self.sequence:04d}-{int(time.time() * 1000) % 100000}"

    def _print_record(self, record):
        print(json.dumps(record, ensure_ascii=False), flush=True)

    def log_call(self, record):
        record["logged_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        self.sink(record)

    def deliver(self, handler, call):
        started = time.monotonic()
        title, level, case, diagnosis, exercise = call
        execution_id = self.new_execution_id()
        hint = build_hint(level, case, diagnosis, exercise)
        summary = f"{title}：用例 {case['id']} 期望 {case.get('expected')}，实际 {case.get('actual')}。"
        session = handler.headers.get("x-hw-agentarts-session-id", "")
        # Record before streaming: a test that reads the reply must never see it before the
        # execution record that explains it, otherwise the same call passes and fails at random.
        self.log_call({
            "mode": self.mode, "request_id": session, "execution_id": execution_id,
            "exercise": exercise, "exercise_title": title, "hint_level": level,
            "case_id": case["id"], "hint_length": len(hint),
            "prepare_ms": round((time.monotonic() - started) * 1000, 3),
        })
        try:
            self.replay(handler, execution_id, case, hint, summary)
        except OSError:
            pass  # The caller timed out and hung up; the real service would see the same.

    def replay(self, handler, execution_id, case, hint, summary):
        if self.mode == "http-500":
            handler.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "模拟运行时故障。"})
            return
        if self.mode == "slow":
            time.sleep(self.slow_seconds)
        handler.stream_open()
        if self.mode == "bad-json":
            handler.wfile.write(b'data: {"event": "workflow_finished", "data": {"outputs": \r\n\r\n')
            handler.wfile.flush()
            return
        for event in build_events(self.mode, execution_id, case["id"], summary, hint):
            handler.send_event(event)
        handler.wfile.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8931, help="本机端口，默认 8931")
    parser.add_argument("--host", default="127.0.0.1", help="仅允许回环地址")
    parser.add_argument("--mode", choices=MODES, default="ok",
                        help="ok 正常返回；其余模式模拟各种云端异常，用于验证回退")
    parser.add_argument("--api-key", default="dev-mock-key", help="模拟入站认证用的 Key")
    parser.add_argument("--slow-seconds", type=float, default=9.0,
                        help="slow 模式下在首个事件前的等待秒数，默认 9（超过客户端 8 秒上限）")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("模拟服务只监听回环地址，请把 --host 设为 127.0.0.1")
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须是 1–65535")
    if not _API_KEY_PATTERN.fullmatch(args.api_key):
        parser.error("--api-key 只能使用字母、数字、点、下划线和连字符")
    with MockServer((args.host, args.port), args.mode, args.api_key, args.slow_seconds) as server:
        host = "127.0.0.1" if args.host == "localhost" else args.host
        url = f"http://{host}:{server.server_port}/runtimes/ai-lab-average/invocations"
        print(f"AgentArts 模拟服务（{args.mode}）已启动", flush=True)
        print(f"  AGENTARTS_WORKFLOW_URL = {url}", flush=True)
        print(f"  AGENTARTS_API_KEY      = {args.api_key}（仅本机模拟，不是真实凭据）", flush=True)
        print("  模式非 ok 时返回异常数据，用来验证页面回退到本地规则。", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
