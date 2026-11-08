"""Baidu accurate OCR. Explicit opt-in; fixed HTTPS endpoints; no automatic retry."""
import base64
import binascii
import hashlib
import json
import math
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_IMAGE_BYTES = 2 * 1024 * 1024
_cache = {}
_lock = threading.Lock()


class OCRError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def enabled():
    return (os.environ.get("BAIDU_OCR_ENABLED") == "1"
            and bool(os.environ.get("BAIDU_OCR_API_KEY", "").strip())
            and bool(os.environ.get("BAIDU_OCR_SECRET_KEY", "").strip()))


def _post(url, fields):
    body = urlencode(fields).encode("ascii")
    request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ValueError("response too large")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("response type")
        return data
    except HTTPError as error:
        error.close()
        raise OCRError(502, "百度OCR服务请求失败，请检查控制台授权与额度") from None
    except (TimeoutError, URLError, OSError, ValueError, RecursionError):
        raise OCRError(502, "百度OCR暂不可用，未自动重试；可改用粘贴资料") from None


def recognize(image):
    if not enabled():
        raise OCRError(503, "百度OCR未配置；请先使用文本录入")
    if not isinstance(image, str) or not image or len(image) > ((MAX_IMAGE_BYTES + 2)//3)*4:
        raise OCRError(400, "仅接受2MiB以内的JPEG或PNG图片")
    try:
        raw = base64.b64decode(image, validate=True)
    except (ValueError, binascii.Error):
        raise OCRError(400, "图片编码无效") from None
    if len(raw) > MAX_IMAGE_BYTES or not (raw.startswith(b"\x89PNG\r\n\x1a\n") or raw.startswith(b"\xff\xd8\xff")):
        raise OCRError(400, "仅接受2MiB以内的JPEG或PNG图片")
    if len(urlencode({"image": image}).encode("ascii")) > 4 * 1024 * 1024:
        raise OCRError(413, "图片编码后过大，请压缩图片")
    if not _lock.acquire(blocking=False):
        raise OCRError(429, "已有图片正在识别，请稍后手动重试")
    try:
        key = os.environ["BAIDU_OCR_API_KEY"].strip()
        secret = os.environ["BAIDU_OCR_SECRET_KEY"].strip()
        fingerprint = hashlib.sha256((key + "\0" + secret).encode()).hexdigest()
        cached = _cache.get(fingerprint)
        if not cached or cached[1] <= time.monotonic():
            data = _post("https://aip.baidubce.com/oauth/2.0/token",
                         {"grant_type": "client_credentials", "client_id": key, "client_secret": secret})
            access = data.get("access_token")
            expiry = data.get("expires_in")
            if not isinstance(access, str) or not access or len(access) > 4096 or not isinstance(expiry, (int, float)) or isinstance(expiry, bool) or not math.isfinite(expiry) or expiry <= 60:
                raise OCRError(502, "百度OCR鉴权失败，请检查应用API Key与Secret Key")
            _cache.clear()
            _cache[fingerprint] = (access, time.monotonic() + min(expiry - 60, 2591940))
        access = _cache[fingerprint][0]
        data = _post("https://aip.baidubce.com/rest/2.0/ocr/v1/accurate_basic?" + urlencode({"access_token": access}),
                     {"image": image, "detect_direction": "true"})
        if "error_code" in data or "error" in data:
            _cache.clear()
            raise OCRError(502, "百度OCR返回错误，请检查应用权限、图片与额度；未自动重试")
        words = data.get("words_result")
        if not isinstance(words, list) or not words or len(words) > 4000:
            raise OCRError(502, "未识别到可用文字，请重新拍照或粘贴资料")
        lines = []
        for item in words:
            if not isinstance(item, dict) or not isinstance(item.get("words"), str):
                raise OCRError(502, "百度OCR响应格式无效")
            lines.append(item["words"])
        text = "\n".join(lines)
        try:
            text.encode("utf-8")
        except UnicodeError:
            raise OCRError(502, "百度OCR响应编码无效") from None
        if not text.strip() or len(text) > 20000:
            raise OCRError(502, "识别文字为空或超过20000字，请拆分资料")
        log_id = data.get("log_id", "")
        return {"text": text, "log_id": str(log_id)[:80] if isinstance(log_id, (str, int)) else ""}
    finally:
        _lock.release()
