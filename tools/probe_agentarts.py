"""One-shot diagnosis of a configured AgentArts workflow endpoint.

Run this the moment a real integration starts returning 本地规则 everywhere. It checks the
configuration, the network path, the raw event stream and the production hint path in that
order, then says which layer failed and what to change. The API key is read from the
environment only and never printed.

    python -B tools/probe_agentarts.py                       # 用已配置的环境变量
    python -B tools/probe_agentarts.py --exercise sum --level 3 --variants
    python -B tools/probe_agentarts.py --url http://127.0.0.1:8931/runtimes/ai-lab-average/invocations

Exit code 0 means the production path really returned a cloud hint; 1 means it fell back;
2 means the endpoint was not configured at all.
"""

import argparse
import json
import logging
import os
import socket
import ssl
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agentarts
from exercise import EXERCISES, check_submission
from tools.start import load_env

MAX_STREAM_BYTES = 64 * 1024
UNDISCLOSED_HEADERS = ("X-Request-Id", "X-Invoke-Mode")


class _NoRedirect(HTTPRedirectHandler):
    """Report a 3xx as what it is instead of silently following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def say(verdict, text, action=None):
    print(f"[{verdict:<4}] {text}")
    if action:
        print(f"        下一步：{action}")


def request_headers(api_key, request_id):
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-hw-agentarts-session-id": request_id,
        "X-Request-Id": request_id,
        "X-Invoke-Mode": "published",
    }


def payload_for(exercise_id, level, timeout_hint=None):
    """Build the same evidence body the product sends, from a real failing submission."""
    result = check_submission(EXERCISES[exercise_id]["starter_code"], exercise_id)
    failed = [case for case in result["cases"] if case["status"] != "passed"]
    inputs = {
        "exercise_title": EXERCISES[exercise_id]["title"],
        "evidence_json": json.dumps(agentarts.evidence_payload(result), ensure_ascii=False),
        "hint_level": level,
    }
    cloud = agentarts._cloud_exercises()
    if len(cloud) > 1:
        inputs["exercise_id"] = exercise_id
    query = os.environ.get("AGENTARTS_QUERY", "").strip()
    if query:
        inputs["query"] = query
    return {"inputs": inputs}, result, failed


def check_configuration(url, api_key):
    if not url or not api_key:
        say("FAIL", "未配置 AGENTARTS_WORKFLOW_URL 或 AGENTARTS_API_KEY。",
            "在启动服务的同一个 PowerShell 窗口里按 README 设置两个环境变量。")
        return False
    parsed = urlsplit(url)
    say("INFO", f"调用地址主机 {parsed.hostname}，路径 {parsed.path or '/'}，Key 长度 {len(api_key)}（不打印）。")
    try:
        agentarts._require_supported_endpoint(url)
    except agentarts.InvalidEndpoint:
        say("FAIL", "地址被客户端判定为不安全：非 HTTPS 且不是本机回环，请求不会发出。",
            "确认复制的是控制台里的完整 HTTPS 调用路径。")
        return False
    say("PASS", "地址通过 HTTPS 校验。")
    cloud = sorted(agentarts._cloud_exercises())
    say("INFO" if len(cloud) > 1 else "WARN", f"当前走云端的题目：{', '.join(cloud)}。",
        None if len(cloud) > 1 else "已按 AGENTARTS_EXERCISES 收窄到单题；要恢复全部三道题，删除该变量。")
    return True


def _peer_subject(connection):
    try:
        return connection.getpeercert()["subject"][-1][0][1]
    except (KeyError, IndexError, TypeError, ValueError):
        return "未知"


def check_network(url, timeout):
    parsed = urlsplit(url)
    host, port = parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)
    started = time.monotonic()
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as error:
        say("FAIL", f"域名解析失败：{error}", "检查本机能否访问该域名，以及是否需要代理。")
        return False
    dns_ms = round((time.monotonic() - started) * 1000)
    say("PASS", f"DNS 解析到 {infos[0][4][0]}，用时 {dns_ms} ms。")
    started = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            tcp_ms = round((time.monotonic() - started) * 1000)
    except OSError as error:
        say("FAIL", f"TCP 连接失败：{error}", "确认端口开放、防火墙与代理设置。")
        return False
    say("PASS", f"TCP 连接用时 {tcp_ms} ms。")
    if parsed.scheme != "https":
        say("INFO", "本机回环明文地址，跳过 TLS 检查。")
        return True
    started = time.monotonic()
    context = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as plain:
            with context.wrap_socket(plain, server_hostname=host) as tls:
                tls_ms = round((time.monotonic() - started) * 1000)
                say("PASS", f"TLS 握手成功，证书主体 {_peer_subject(tls)}，用时 {tls_ms} ms。")
    except ssl.SSLError as error:
        say("FAIL", f"TLS 握手失败：{error}", "多为证书链或 SNI 问题，先用浏览器打开同一地址确认。")
        return False
    except OSError as error:
        say("FAIL", f"TLS 连接异常：{error}")
        return False
    return True


def collect_events(response, deadline):
    events, buffered = [], 0
    for line in response:
        buffered += len(line)
        if buffered > MAX_STREAM_BYTES or time.monotonic() > deadline:
            say("WARN", "响应流超出读取上限或到达时间上限，已停止读取。")
            break
        if not line.startswith(b"data:"):
            continue
        try:
            event = json.loads(line[5:])
        except ValueError:
            events.append({"event": "!broken-json", "raw": line[5:85].decode("utf-8", "replace")})
            continue
        if isinstance(event, dict):
            events.append(event)
            if event.get("event") in ("workflow_finished", "error", "exception", "end"):
                break
    return events


def describe_stream(events, elapsed_ms):
    names = [event.get("event", "?") for event in events]
    say("INFO", f"事件顺序：{' → '.join(names) or '（空）'}，用时 {elapsed_ms} ms。")
    if not events:
        say("FAIL", "没有收到任何 data: 事件。", "确认返回的是 text/event-stream，而不是网关的 HTML 错误页。")
        return
    broken = [event for event in events if event.get("event") == "!broken-json"]
    if broken:
        say("FAIL", f"事件不是合法 JSON：{broken[0]['raw'][:60]}", "检查大模型节点是否关闭了流式输出。")
        return
    for event in events:
        if event.get("event") in ("error", "exception"):
            data = event.get("data") or {}
            say("FAIL", f"工作流返回 {event['event']}：{data.get('error_code') or data.get('message') or data}",
                "到控制台按 execution_id 查看该节点的报错与输入。")
            return
    finished = next((event for event in events if event.get("event") == "workflow_finished"), None)
    if finished is None:
        say("FAIL", "流里没有 workflow_finished 事件。", "确认结束节点已配置并部署到实例，而不是只保存了草稿。")
        return
    data = finished.get("data") or {}
    status = data.get("status") or {}
    say("INFO" if status.get("desc") == "succeeded" else "FAIL",
        f"结束状态 code={status.get('code')} desc={status.get('desc')}，execution_id={data.get('execution_id')}。",
        None if status.get("desc") == "succeeded" else "等待态或失败态不会被接受，检查节点是否真的跑完。")
    outputs = data.get("outputs") or {}
    fields = outputs.get("user_fields")
    if not isinstance(fields, dict) or not fields:
        say("FAIL", "outputs.user_fields 缺失或为空。",
            "结束节点需把 hint、case_id 绑定到教学提示节点与诊断节点的同名字段，大模型节点选择 JSON 格式。")
        return
    say("PASS" if {"hint", "case_id"} <= set(fields) else "FAIL",
        f"user_fields 字段：{sorted(fields)}。",
        None if {"hint", "case_id"} <= set(fields) else "字段名必须正好是 hint 和 case_id，客户端按名字取值。")
    hint = fields.get("hint")
    if isinstance(hint, str):
        say("INFO", f"hint 长度 {len(hint)} 字，前 40 字：{hint[:40]}")
        if len(hint) > 240:
            say("WARN", "hint 超过 240 字，客户端会拒绝并回退。", "在提示词里限定一句话。")
        if agentarts._SOLUTION.search(hint):
            say("WARN", "hint 含代码片段，客户端会判定为泄露答案并回退。", "教学提示节点应只给排查方向。")


def probe_call(url, api_key, body, headers, timeout):
    opener = build_opener(_NoRedirect)
    request = Request(url, json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers, method="POST")
    started = time.monotonic()
    try:
        with opener.open(request, timeout=timeout) as response:
            events = collect_events(response, started + timeout)
            return response.status, response.headers.get("Content-Type", ""), events, round((time.monotonic() - started) * 1000)
    except HTTPError as error:
        detail = error.read(400).decode("utf-8", "replace")[:200] if error.fp else ""
        error.close()
        return error.code, error.headers.get("Content-Type", "") if error.headers else "", [{"event": "!http-error", "raw": detail}], round((time.monotonic() - started) * 1000)
    except (URLError, OSError, ssl.SSLError) as error:
        return None, "", [{"event": "!transport-error", "raw": str(error)[:200]}], round((time.monotonic() - started) * 1000)


class _RecordCollector(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def probe_production(exercise_id, level):
    """Drive the real product path and read back what it decided."""
    logger = logging.getLogger("agentarts")
    collector = _RecordCollector()
    previous = (logger.propagate, logger.level)
    logger.propagate, logger.level = False, logging.INFO
    logger.addHandler(collector)
    started = time.monotonic()
    try:
        result = check_submission(EXERCISES[exercise_id]["starter_code"], exercise_id)
        reply = agentarts.get_hint(exercise_id, result, level)
    finally:
        logger.removeHandler(collector)
        logger.propagate, logger.level = previous
    record = json.loads(collector.messages[-1]) if collector.messages else {}
    elapsed_ms = round((time.monotonic() - started) * 1000)
    reason = record.get("fallback_reason")
    if reply["source"] == "agentarts":
        say("PASS", f"生产路径命中云端，用时 {elapsed_ms} ms，execution_id={record.get('execution_id')}。")
    else:
        say("FAIL", f"生产路径回退到本地规则，原因 {reason}，用时 {elapsed_ms} ms。")
    say("INFO", f"页面会显示：{reply['hint'][:60]}")
    return reply["source"] == "agentarts", reason


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", help="覆盖 AGENTARTS_WORKFLOW_URL，便于对照测试")
    parser.add_argument("--exercise", choices=sorted(EXERCISES), default="average")
    parser.add_argument("--level", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--timeout", type=float, default=20.0, help="探针自身的等待上限，默认 20 秒")
    parser.add_argument("--variants", action="store_true",
                        help="额外验证未文档化请求头与 query 字段是否被网关接受")
    parser.add_argument("--skip-network", action="store_true")
    parser.add_argument("--export-inputs", type=Path, help="导出控制台试运行参数，无需 Key 或网络")
    args = parser.parse_args()
    if not 0.5 <= args.timeout <= 120:
        parser.error("--timeout 需在 0.5 到 120 秒之间")
    if args.export_inputs:
        body, _, _ = payload_for(args.exercise, args.level)
        args.export_inputs.write_text(json.dumps(body["inputs"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        say("PASS", f"试运行参数已导出到 {args.export_inputs}")
        return 0

    try:
        load_env(ROOT / ".env", os.environ)
    except (ValueError, OSError) as error:
        say("FAIL", f".env 读取失败：{error}", "修正 .env 后重试；已存在的环境变量优先。")
        return 2
    agentarts.refresh_timeout()

    url = (args.url or os.environ.get("AGENTARTS_WORKFLOW_URL", "")).strip()
    api_key = os.environ.get("AGENTARTS_API_KEY", "").strip()
    if args.url:
        os.environ["AGENTARTS_WORKFLOW_URL"] = url  # keep the production path on the same endpoint
    print(f"AgentArts 端点探针 · 题目 {args.exercise} · 提示等级 {args.level}")
    if not check_configuration(url, api_key):
        return 2
    if not args.skip_network and not check_network(url, args.timeout):
        return 1

    body, _, failed = payload_for(args.exercise, args.level)
    request_id = uuid4().hex
    status, content_type, events, elapsed_ms = probe_call(url, api_key, body, request_headers(api_key, request_id),
                                                          args.timeout)
    print(f"--- 传输层：HTTP {status}，Content-Type {content_type or '未知'} ---")
    if status is None:
        say("FAIL", f"请求未能完成：{events[0]['raw']}", "确认地址、代理与防火墙。")
    elif status != 200:
        say("FAIL", f"网关返回 HTTP {status}：{events[0].get('raw', '')}",
            "401/403 查 Key 与是否发布到实例；404 查调用路径是否为运行时 invocations 地址。")
    elif not content_type.startswith("text/event-stream"):
        say("WARN", f"返回类型不是 text/event-stream：{content_type}", "可能是中间层缓冲了响应。")
    else:
        describe_stream(events, elapsed_ms)
    if elapsed_ms > agentarts._TIMEOUT * 1000:
        say("WARN", f"本次耗时 {elapsed_ms} ms 已超过生产路径的 {agentarts._TIMEOUT} 秒上限。",
            "真实调用必然超时回退，需要精简提示词或调大 agentarts._TIMEOUT。")

    if args.variants:
        print("--- 风险探针：未文档化请求头与 query 字段 ---")
        trimmed = {name: value for name, value in request_headers(api_key, request_id).items()
                   if name not in UNDISCLOSED_HEADERS}
        trimmed_status, _, trimmed_events, _ = probe_call(url, api_key, body, trimmed, args.timeout)
        with_query = {"inputs": {**body["inputs"], "query": failed[0]["id"]}}
        query_status, _, query_events, _ = probe_call(url, api_key, with_query, request_headers(api_key, request_id),
                                                      args.timeout)
        for label, variant_status, variant_events in (("去掉未文档化请求头", trimmed_status, trimmed_events),
                                                      ("额外发送 query 字段", query_status, query_events)):
            if variant_status == status:
                say("INFO", f"{label}：HTTP {variant_status}，与基线一致。")
            else:
                say("WARN", f"{label}：HTTP {variant_status}，基线为 HTTP {status}。",
                    "两种载荷都能跑通时优先保留与文档一致的那一种。")

    print("--- 生产路径 ---")
    reached_cloud, reason = probe_production(args.exercise, args.level)
    if not reached_cloud:
        say("INFO", f"对照表见 docs/agentarts-integration-checklist.md 的回退原因一节，本次原因 {reason}。")
    return 0 if reached_cloud else 1


if __name__ == "__main__":
    sys.exit(main())
