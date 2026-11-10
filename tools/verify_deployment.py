"""Black-box acceptance for a real trial deployment.

Verifies what repository checks cannot: certificate validity, HTTP-to-HTTPS
redirect, unauthenticated rejection, health isolation and the authenticated
page. Run it from a machine that can reach the public host, after nginx and
the systemd unit are enabled. It never prints the basic-auth password.
"""

import argparse
import base64
import json
import socket
import ssl
import sys
import time
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.parse import urlsplit

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
CERT_WARN_DAYS = 14
REDIRECTS = {301, 302, 307, 308}


def check(name, verdict, detail):
    return {"name": name, "verdict": verdict, "detail": detail}


def target_parts(target):
    parts = urlsplit(target)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("地址需为 http:// 或 https:// 开头并包含主机名")
    if parts.query or parts.fragment or parts.path not in ("", "/"):
        raise ValueError("只填站点根地址，例如 https://trial.example.com")
    if parts.scheme == "http" and parts.hostname not in LOOPBACK:
        raise ValueError("公网地址必须使用 HTTPS；明文 HTTP 仅允许本机演练")
    return parts


def call(parts, method="GET", path="/", headers=None, body=None, timeout=15):
    port = parts.port or (443 if parts.scheme == "https" else 80)
    klass = HTTPSConnection if parts.scheme == "https" else HTTPConnection
    connection = klass(parts.hostname, port, timeout=timeout)
    started = time.monotonic()
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read(4096)
        return {
            "status": response.status,
            "location": response.getheader("Location") or "",
            "body": payload.decode("utf-8", "replace"),
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
    finally:
        connection.close()


def certificate(parts, timeout=15):
    port = parts.port or 443
    context = ssl.create_default_context()
    with socket.create_connection((parts.hostname, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=parts.hostname) as tls:
            return tls.getpeercert()


def certificate_check(parts, results, timeout):
    try:
        cert = certificate(parts, timeout)
        expires = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        days = (expires - datetime.now(timezone.utc)).days
        verdict = "PASS" if days > CERT_WARN_DAYS else "WARN"
        results.append(check("TLS 证书", verdict,
                             f"主机 {parts.hostname} 证书有效，剩余 {days} 天（{expires.date()} 到期）"))
    except (OSError, ssl.SSLError, KeyError, ValueError) as error:
        results.append(check("TLS 证书", "FAIL", f"{type(error).__name__}: {str(error)[:160]}"))


def redirect_check(parts, results, timeout):
    if parts.scheme != "https":
        results.append(check("HTTP 跳转 HTTPS", "SKIP", "本机 HTTP 演练不检查跳转"))
        return
    port = parts.port or 443
    plain = urlsplit(f"http://{parts.hostname}" + (f":{port}" if parts.port and parts.port != 443 else ""))
    try:
        response = call(plain, timeout=timeout)
        location = response["location"]
        ok = response["status"] in REDIRECTS and location.startswith("https://")
        results.append(check("HTTP 跳转 HTTPS", "PASS" if ok else "FAIL",
                             f"HTTP {response['status']}，Location={location or '（空）'}"))
    except OSError as error:
        results.append(check("HTTP 跳转 HTTPS", "FAIL", f"{type(error).__name__}: {str(error)[:160]}"))


def unauthenticated_checks(parts, results, timeout):
    probes = [
        ("未登录访问首页", "GET", "/", None),
        ("未登录访问题库", "GET", "/api/exercises", None),
        ("未登录提交判题", "POST", "/api/check", json.dumps({"code": "x"})),
        ("未登录请求提示", "POST", "/api/hint", json.dumps({"exercise_id": "average", "code": "x", "level": 1})),
    ]
    headers = {"Content-Type": "application/json"}
    for name, method, path, body in probes:
        try:
            response = call(parts, method, path, headers if body else None, body, timeout)
            results.append(check(name, "PASS" if response["status"] == 401 else "FAIL",
                                 f"HTTP {response['status']}（期望 401）"))
        except OSError as error:
            results.append(check(name, "FAIL", f"{type(error).__name__}: {str(error)[:120]}"))
    forged = {"X-Forwarded-User": "admin", "X-Remote-User": "admin",
              "X-Forwarded-Authorization": "Bearer forged"}
    try:
        response = call(parts, "GET", "/", forged, None, timeout)
        results.append(check("伪造转发身份头", "PASS" if response["status"] == 401 else "FAIL",
                             f"HTTP {response['status']}（期望 401）"))
    except OSError as error:
        results.append(check("伪造转发身份头", "FAIL", f"{type(error).__name__}: {str(error)[:120]}"))
    try:
        response = call(parts, "GET", "/healthz", timeout=timeout)
        results.append(check("健康检查不对外", "PASS" if response["status"] == 403 else "FAIL",
                             f"HTTP {response['status']}（期望 403）"))
    except OSError as error:
        results.append(check("健康检查不对外", "FAIL", f"{type(error).__name__}: {str(error)[:120]}"))


def authenticated_checks(parts, results, user, password, timeout):
    if not user or password is None:
        results.append(check("登录后首页", "SKIP", "未提供 --basic-user 与环境变量密码"))
        results.append(check("登录后题库", "SKIP", "未提供 --basic-user 与环境变量密码"))
        return
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {token}"}
    try:
        page = call(parts, "GET", "/", headers, None, timeout)
        ok = page["status"] == 200 and "智学工坊" in page["body"]
        results.append(check("登录后首页", "PASS" if ok else "FAIL",
                             f"HTTP {page['status']}，页面标记{'存在' if '智学工坊' in page['body'] else '缺失'}"))
        data = call(parts, "GET", "/api/exercises", headers, None, timeout)
        try:
            exercises = json.loads(data["body"])
        except ValueError:
            exercises = None
        ok = data["status"] == 200 and isinstance(exercises, list) and len(exercises) > 0
        results.append(check("登录后题库", "PASS" if ok else "FAIL",
                             f"HTTP {data['status']}，题目数 {len(exercises) if isinstance(exercises, list) else '无法解析'}"))
    except OSError as error:
        results.append(check("登录后首页", "FAIL", f"{type(error).__name__}: {str(error)[:120]}"))


def run(target, timeout=15, user="", password=None):
    parts = target_parts(target)
    results = []
    if parts.scheme == "https":
        certificate_check(parts, results, timeout)
    else:
        results.append(check("TLS 证书", "SKIP", "本机 HTTP 演练不检查证书"))
    redirect_check(parts, results, timeout)
    unauthenticated_checks(parts, results, timeout)
    authenticated_checks(parts, results, user, password, timeout)
    report = {
        "kind": "deployment_acceptance",
        "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "target": f"{parts.scheme}://{parts.netloc}",
        "results": results,
    }
    report["failed"] = sum(item["verdict"] == "FAIL" for item in results)
    report["warned"] = sum(item["verdict"] == "WARN" for item in results)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="真实试用入口的黑盒验收")
    parser.add_argument("--url", required=True, help="站点根地址，例如 https://trial.example.com")
    parser.add_argument("--basic-user", default="", help="nginx basic 认证用户名；省略则跳过登录后检查")
    parser.add_argument("--password-env", default="DEPLOY_BASIC_PASSWORD",
                        help="保存 basic 认证密码的环境变量名，默认 DEPLOY_BASIC_PASSWORD")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--json", type=Path, help="把报告写到该文件")
    args = parser.parse_args(argv)
    password = None
    if args.basic_user:
        import os
        password = os.environ.get(args.password_env)
        if password is None:
            parser.error(f"未找到环境变量 {args.password_env}；不要把密码写在命令行")
    try:
        report = run(args.url, args.timeout, args.basic_user, password)
    except ValueError as error:
        parser.error(str(error))
    for item in report["results"]:
        print(f"[{item['verdict']:<4}] {item['name']}：{item['detail']}")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"结果：{report['failed']} 项失败，{report['warned']} 项警告。")
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())