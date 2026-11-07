"""DeepSeek OpenAI-compatible non-streaming hint adapter."""

from compat import InvalidCompatibleEndpoint, invoke as _invoke

DEFAULT_URL = "https://api.deepseek.com/chat/completions"
InvalidDeepSeekEndpoint = InvalidCompatibleEndpoint


def invoke(opener, url, api_key, model, request_id, title, evidence, level, exercise_id, timeout):
    return _invoke(opener, url, api_key, model, request_id, title, evidence, level,
                   exercise_id, timeout, json_mode=True)