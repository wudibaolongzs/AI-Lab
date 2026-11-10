"""Extract workflow failures from hint logs for console triage.

Only reads the bounded identifiers already written by agentarts: request id,
execution id, cloud error code, failed node and elapsed time. It deliberately
does not print or store model error text or prompt content.
"""

import argparse
import json
from collections import Counter
from pathlib import Path


def collect(paths):
    rows = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or row.get("fallback_reason") != "workflow_failed":
                continue
            rows.append({
                "request_id": row.get("request_id"),
                "execution_id": row.get("execution_id"),
                "cloud_error_code": row.get("cloud_error_code"),
                "failed_node_id": row.get("failed_node_id"),
                "elapsed_ms": row.get("elapsed_ms"),
                "ts": row.get("ts"),
            })
    return rows


def summarise(rows):
    return {
        "failures": len(rows),
        "by_code": dict(Counter(row["cloud_error_code"] or "unknown" for row in rows)),
        "by_node": dict(Counter(row["failed_node_id"] or "unknown" for row in rows)),
        "rows": rows,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="从提示日志提取 workflow_failed 记录")
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="写出机器可读清单")
    args = parser.parse_args(argv)
    rows = collect(args.logs)
    if not rows:
        print("没有 workflow_failed 记录。确认日志文件包含 AI 提示请求行。", file=__import__("sys").stderr)
        return 2
    report = summarise(rows)
    print(f"工作流失败 {report['failures']} 次；按错误码 {report['by_code']}；按节点 {report['by_node']}")
    print("| request_id | execution_id | 错误码 | 失败节点 | 耗时 ms |")
    print("| --- | --- | --- | --- | --- |")
    for row in rows:
        print(f"| {row['request_id'] or ''} | {row['execution_id'] or ''} | "
              f"{row['cloud_error_code'] or ''} | {row['failed_node_id'] or ''} | {row['elapsed_ms']} |")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())