"""One-shot live check for the temporary DeepSeek provider.

Reads configuration from .env (existing process variables win), sends one real hint request
through the production path, and reports whether the key, model and JSON output are usable.
The key is never printed.

    python -B tools/check_deepseek.py --level 2 --exercise average
"""

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import agentarts
import deepseek
from agentarts import get_hint
from exercise import EXERCISES, check_submission
from tools.start import load_env

ADVICE = {
    "not_configured": "检查 .env 中的 DEEPSEEK_API_KEY 与 DEEPSEEK_MODEL 是否已填写。",
    "invalid_endpoint": "DEEPSEEK_API_URL 必须是 https 地址，且不能带账号、密码或 # 片段。",
    "http_error": "401/403 查 Key 是否有效；404 查地址是否为 chat/completions；429 查额度与频率。",
    "timeout": "网络或模型响应过慢，可先用较小模型复测，或加大 --timeout。",
    "connection_error": "检查 DNS、代理和出网策略，确认能访问 api.deepseek.com。",
    "invalid_response": "模型没有返回 JSON 对象。建议 DEEPSEEK_MODEL=deepseek-chat，并确认账号支持 JSON Output。",
    "invalid_output": "返回内容未通过字段或内容检查（单行、240 字内、不含完整答案、case_id 必须来自失败用例）。",
    "invalid_provider": "AI_PROVIDER 必须是 deepseek（或 tencent / agentarts）。",
    "local_exercise": "该题不在 AGENTARTS_EXERCISES 名单内。",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exercise", choices=tuple(EXERCISES), default="average")
    parser.add_argument("--level", type=int, choices=(1, 2, 3), default=2)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    if not 0.5 <= args.timeout <= 120:
        parser.error("--timeout 需在 0.5 到 120 秒之间")
    try:
        load_env(ROOT / ".env", os.environ)
    except (ValueError, OSError) as error:
        print(f".env 读取失败：{error}", file=sys.stderr)
        return 2

    provider = os.environ.get("AI_PROVIDER", "agentarts").strip().lower()
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "").strip()
    url = os.environ.get("DEEPSEEK_API_URL", "").strip() or deepseek.DEFAULT_URL
    problems = []
    if provider != "deepseek":
        problems.append(f"AI_PROVIDER 当前是 {provider or '未设置'}，需改为 deepseek")
    if not key:
        problems.append("DEEPSEEK_API_KEY 未填写")
    if not model:
        problems.append("DEEPSEEK_MODEL 未填写")
    if problems:
        print("配置检查未通过：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 2

    agentarts._TIMEOUT = args.timeout
    print(f"DeepSeek 连通性检查 · 题目 {args.exercise} · 等级 {args.level} · 模型 {model}")
    print(f"端点：{url}")
    result = check_submission(EXERCISES[args.exercise]["starter_code"], args.exercise)
    start = time.monotonic()
    answer = get_hint(args.exercise, result, args.level)
    elapsed = round((time.monotonic() - start) * 1000)
    if answer["source"] != "deepseek":
        reason = answer.get("fallback_reason") or "unknown"
        print(f"FAIL 未命中 DeepSeek，回退原因：{reason}（{elapsed} ms）")
        print(f"建议：{ADVICE.get(reason, '查看上方日志中的 fallback_reason。')}")
        return 1
    print(f"PASS DeepSeek 真实返回成功（{elapsed} ms）")
    print(f"execution_id：{answer.get('execution_id') or '未提供'}")
    print(f"case_id：{answer['case_id']}")
    print(f"提示：{answer['hint']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())