"""Tencent Hunyuan / TokenHub OpenAI-compatible non-streaming hint adapter."""

from compat import InvalidCompatibleEndpoint, invoke as _invoke

DEFAULT_URL = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"
InvalidTencentEndpoint = InvalidCompatibleEndpoint


def invoke(opener, url, api_key, model, request_id, title, evidence, level, exercise_id, timeout):
    return _invoke(opener, url, api_key, model, request_id, title, evidence, level,
                   exercise_id, timeout, json_mode=False)