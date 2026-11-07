import argparse
import json
import logging
import ipaddress
import re
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from socket import timeout as SocketTimeout

from agentarts import get_hint
from exercise import EXERCISE, EXERCISES, check_submission


PAGE = Path(__file__).resolve().with_name("index.html")
MAX_REQUEST_BYTES = 12_288
DRAIN_CEILING = 4 * 1024 * 1024  # never swallow more than this for a body we are about to reject
DRAIN_SECONDS = 0.5  # a client that declares bytes it never writes must not hold a worker open
MAX_LENGTH_DIGITS = len(str(DRAIN_CEILING))


class Handler(BaseHTTPRequestHandler):
    timeout = 5

    def send_body(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_body(status, "application/json; charset=utf-8", body)

    def reject(self, status, message):
        self.send_json(status, {"error": message})

    def is_local_host(self):
        values = self.headers.get_all("Host", [])
        if len(values) == 1 and values[0].lower() in self.server.allowed_hosts:
            return True
        self.reject(HTTPStatus.BAD_REQUEST, "访问地址不在服务的 Host 白名单中。")
        return False

    def do_GET(self):
        if not self.is_local_host():
            return
        path = self.path.partition("?")[0]
        if path == "/":
            self.send_body(HTTPStatus.OK, "text/html; charset=utf-8", PAGE.read_bytes())
        elif path == "/api/exercise":
            self.send_json(HTTPStatus.OK, EXERCISE)
        elif path == "/api/exercises":
            self.send_json(HTTPStatus.OK, [{"id": key, **exercise} for key, exercise in EXERCISES.items()])
        else:
            self.reject(HTTPStatus.NOT_FOUND, "页面或接口不存在。")

    def drain_body(self, limit):
        """Read and discard up to limit body bytes, giving up quickly on a client that never sends them."""
        previous = self.connection.gettimeout()
        self.connection.settimeout(DRAIN_SECONDS)
        deadline = time.monotonic() + DRAIN_SECONDS
        try:
            remaining = limit
            while remaining > 0 and time.monotonic() < deadline:
                chunk = self.rfile.read(min(8192, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (SocketTimeout, OSError):
            pass
        finally:
            self.connection.settimeout(previous)

    def read_post_payload(self):
        lengths = self.headers.get_all("Content-Length", [])
        length = lengths[0].strip(" \t") if len(lengths) == 1 else ""
        if not length.isascii() or not length.isdigit() or "Transfer-Encoding" in self.headers:
            self.reject(HTTPStatus.BAD_REQUEST, "请求体长度无效。")
            return
        length = length.lstrip("0") or "0"
        declared = int(length) if len(length) <= MAX_LENGTH_DIGITS else DRAIN_CEILING
        if declared > MAX_REQUEST_BYTES:
            # Discard what the client is still writing first: closing with bytes in flight can
            # reset the connection on Windows and the browser would never see this answer. The
            # ceiling only caps a pathological claim; a real oversized body is drained in full.
            self.drain_body(min(declared, DRAIN_CEILING))
            try:
                self.reject(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "提交内容过长。")
            except OSError:
                self.close_connection = True
            return

        try:
            body = self.rfile.read(declared)
        except SocketTimeout:
            self.reject(HTTPStatus.REQUEST_TIMEOUT, "读取请求体超时。")
            return
        if len(body) != declared:
            self.reject(HTTPStatus.BAD_REQUEST, "请求体不完整。")
            return
        # Closing the connection with unread body bytes can discard the response on Windows.
        if self.headers.get_content_type() != "application/json":
            self.reject(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "请提交 JSON。")
            return
        try:
            payload = json.loads(body.decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("code"), str):
                raise ValueError
            payload["code"].encode("utf-8")
        except (ValueError, RecursionError):
            self.reject(HTTPStatus.BAD_REQUEST, "请提供有效的 UTF-8 文本字段 code。")
            return
        return payload

    def do_POST(self):
        if not self.is_local_host():
            return
        if self.path not in ("/api/check", "/api/hint"):
            self.reject(HTTPStatus.NOT_FOUND, "接口不存在。")
            return
        payload = self.read_post_payload()
        if payload is None:
            return

        is_hint = self.path == "/api/hint"
        exercise_id = payload.get("exercise_id", None if is_hint else "average")
        if not isinstance(exercise_id, str) or exercise_id not in EXERCISES:
            self.reject(HTTPStatus.BAD_REQUEST, "请选择题库中的练习。")
            return
        level = payload.get("level")
        if is_hint and (type(level) is not int or not 1 <= level <= 3):
            self.reject(HTTPStatus.BAD_REQUEST, "提示等级必须是 1 到 3 的整数。")
            return
        result = check_submission(payload["code"], exercise_id)
        if is_hint:
            if result["status"] != "failed":
                self.reject(HTTPStatus.CONFLICT, "只有测试未通过的有效提交可以获取提示。")
                return
            result = get_hint(exercise_id, result, level)
        self.send_json(HTTPStatus.OK, result)


def create_server(port, host="127.0.0.1", allowed_hosts=()):
    address = ipaddress.IPv4Address(host)
    names = {"127.0.0.1", "localhost"}
    for name in allowed_hosts:
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", name):
            raise ValueError("Host 白名单需填写 IPv4 地址或主机名，不含协议、端口或通配符。")
        names.add(name.lower())
    if not address.is_loopback and not allowed_hosts:
        raise ValueError("对外监听需显式提供 --allow-host。")
    server = ThreadingHTTPServer((str(address), port), Handler)
    server.allowed_hosts = {f"{name}:{server.server_port}" for name in names}
    if server.server_port == 80:
        server.allowed_hosts.update(names)
    return server


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="启动智学工坊 AI-Lab 本地原型。")
    parser.add_argument("--port", type=int, default=8000, help="本机端口，默认 8000")
    parser.add_argument("--host", default="127.0.0.1", help="监听 IPv4，默认仅本机")
    parser.add_argument("--allow-host", action="append", default=[], help="额外允许的主机名或 IPv4，可重复")
    args = parser.parse_args()
    try:
        server = create_server(args.port, args.host, args.allow_host)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    with server:
        print(f"AI-Lab 运行中：http://127.0.0.1:{server.server_port}", flush=True)
        print(f"监听 {args.host}，允许访问 {', '.join(sorted(server.allowed_hosts))}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
