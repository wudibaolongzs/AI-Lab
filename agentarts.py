"""Request one evidence-based hint from a published AgentArts workflow."""

import json
import logging
import os
import re
import socket
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

from deepseek import DEFAULT_URL as DEEPSEEK_DEFAULT_URL, InvalidDeepSeekEndpoint, invoke as invoke_deepseek
from exercise import EXERCISES
from tencent import DEFAULT_URL as TENCENT_DEFAULT_URL, InvalidTencentEndpoint, invoke as invoke_tencent


_LOG = logging.getLogger(__name__)
_DEFAULT_TIMEOUT = 8.0


def _configured_timeout(raw=None):
    """Read AI_TIMEOUT; invalid or out-of-range values fall back to 8 seconds."""
    raw = os.environ.get("AI_TIMEOUT", "") if raw is None else raw
    try:
        value = float(str(raw).strip())
    except ValueError:
        return _DEFAULT_TIMEOUT
    return value if 1 <= value <= 120 else _DEFAULT_TIMEOUT


_TIMEOUT = _configured_timeout()
_MAX_STREAM_BYTES = 128 * 1024
_MAX_HINT_LENGTH = 240  # one sentence is enough to point at the next check
_EXECUTION_ID = re.compile(r"[A-Za-z0-9_.:-]{1,100}")
_SOLUTION = re.compile(r"```|\b(?:def|return)\s+|\bsum\s*\([^)]*\)\s*/\s*len\s*\(", re.I | re.ASCII)
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_DEFAULT_CLOUD_EXERCISES = frozenset(EXERCISES)


class InvalidEndpoint(ValueError):
    """Raised when the configured workflow URL cannot be called safely."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_NoRedirect)


def _workflow_result(response, deadline):
    remaining = _MAX_STREAM_BYTES
    while remaining > 0:
        line = response.readline(remaining + 1)
        if time.monotonic() >= deadline:
            raise TimeoutError
        remaining -= len(line)
        if not line or remaining < 0:
            break
        if not line.startswith(b"data:"):
            continue
        event = json.loads(line[5:])
        if not isinstance(event, dict) or event.get("event") in ("error", "exception", "end"):
            break
        if event.get("event") != "workflow_finished":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            break
        status = data.get("status")
        outputs = data.get("outputs")
        if (
            isinstance(status, dict) and status.get("code") == 1
            and status.get("desc") == "succeeded" and isinstance(outputs, dict)
        ):
            execution_id = data.get("execution_id")
            if not isinstance(execution_id, str) or not _EXECUTION_ID.fullmatch(execution_id):
                execution_id = None
            return outputs.get("user_fields"), execution_id
        break
    return None, None


def _require_supported_endpoint(url):
    """Reject anything that would send the runtime API key over a clear-text channel."""
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username is not None:
        raise InvalidEndpoint("invalid endpoint")
    if parsed.scheme == "http" and parsed.hostname not in _LOOPBACK_HOSTS:
        raise InvalidEndpoint("invalid endpoint")


def _cloud_exercises():
    """Exercises whose hints may go to the workflow; setting the switch narrows the default.

    Every exercise leaves the machine by default. AGENTARTS_EXERCISES can still narrow that set,
    and a one-exercise set keeps the documented three-field payload for older workflows.
    """
    names = {name.strip() for name in os.environ.get("AGENTARTS_EXERCISES", "").split(",") if name.strip()}
    return (names & set(EXERCISES)) or _DEFAULT_CLOUD_EXERCISES


def _invoke(url, api_key, request_id, title, evidence, level, exercise_id=None):
    _require_supported_endpoint(url)
    inputs = {
        "exercise_title": title,
        "evidence_json": json.dumps(evidence, ensure_ascii=False),
        "hint_level": level,
    }
    if exercise_id is not None:
        inputs["exercise_id"] = exercise_id
    body = {"inputs": inputs}
    request = Request(url, json.dumps(body, ensure_ascii=False).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "x-hw-agentarts-session-id": request_id,
        "X-Request-Id": request_id,
        "X-Invoke-Mode": "published",
    }, method="POST")
    deadline = time.monotonic() + _TIMEOUT
    with _OPENER.open(request, timeout=_TIMEOUT) as response:
        return _workflow_result(response, deadline)


def get_hint(exercise_id, result, level):
    """Select a hint for an already validated failing submission."""
    start = time.monotonic()
    request_id = uuid4().hex
    failed = [case for case in result["cases"] if case["status"] != "passed"]
    reply = {
        "hint": result["hints"][level - 1], "case_id": failed[0]["id"],
        "source": "local", "request_id": request_id,
    }
    provider = os.environ.get("AI_PROVIDER", "agentarts").strip().lower()
    url = os.environ.get("AGENTARTS_WORKFLOW_URL", "").strip()
    api_key = os.environ.get("AGENTARTS_API_KEY", "").strip()
    model = ""
    if provider == "tencent":
        url = os.environ.get("TENCENT_API_URL", "").strip() or TENCENT_DEFAULT_URL
        api_key = os.environ.get("TENCENT_API_KEY", "").strip()
        model = os.environ.get("TENCENT_MODEL", "").strip()
    elif provider == "deepseek":
        url = os.environ.get("DEEPSEEK_API_URL", "").strip() or DEEPSEEK_DEFAULT_URL
        api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        model = os.environ.get("DEEPSEEK_MODEL", "").strip()
    execution_id = None
    cloud = _cloud_exercises()
    reason = "local_exercise" if exercise_id not in cloud else "not_configured"
    if provider not in ("agentarts", "tencent", "deepseek"):
        reason = "invalid_provider"
    elif exercise_id in cloud and url and api_key and (provider == "agentarts" or model):
        try:
            if provider == "tencent":
                fields, execution_id = invoke_tencent(
                    _OPENER, url, api_key, model, request_id, EXERCISES[exercise_id]["title"],
                    {"cases": failed, "diagnosis": result["diagnosis"]}, level, exercise_id, _TIMEOUT)
            elif provider == "deepseek":
                fields, execution_id = invoke_deepseek(
                    _OPENER, url, api_key, model, request_id, EXERCISES[exercise_id]["title"],
                    {"cases": failed, "diagnosis": result["diagnosis"]}, level, exercise_id, _TIMEOUT)
            else:
                fields, execution_id = _invoke(url, api_key, request_id, EXERCISES[exercise_id]["title"],
                                           {"cases": failed, "diagnosis": result["diagnosis"]}, level,
                                           exercise_id if len(cloud) > 1 else None)
            hint = fields.get("hint") if isinstance(fields, dict) else None
            case_id = fields.get("case_id") if isinstance(fields, dict) else None
            if (isinstance(hint, str) and 0 < len(hint.strip()) <= _MAX_HINT_LENGTH and len(hint.strip().splitlines()) == 1
                    and not _SOLUTION.search(hint) and case_id in [case["id"] for case in failed]):
                reply.update(hint=hint.strip(), case_id=case_id, source=provider)
                reason = None
            else:
                reason = "invalid_output"
        except HTTPError as error:
            error.close()
            reason = "http_error"
        except (TimeoutError, socket.timeout):
            reason = "timeout"
        except URLError as error:
            reason = "timeout" if isinstance(error.reason, (TimeoutError, socket.timeout)) else "connection_error"
        except (OSError, HTTPException):
            reason = "connection_error"
        except (InvalidEndpoint, InvalidTencentEndpoint, InvalidDeepSeekEndpoint):
            reason = "invalid_endpoint"
        except (ValueError, RecursionError):
            reason = "invalid_response"
    reply["fallback_reason"] = reason
    reply["execution_id"] = execution_id
    _LOG.info(json.dumps({
        "request_id": request_id, "source": reply["source"],
        "elapsed_ms": round((time.monotonic() - start) * 1000),
        "fallback_reason": reason, "execution_id": execution_id,
    }))
    return reply
