"""Summarise structured AI log lines: cloud rate, fallbacks, latency and budget.

Reads the JSON lines written by agentarts.get_hint (one per hint request).
Use it after a trial session to answer three questions: how often did the
cloud answer, why did the rest fall back, and how slow was the slow tail.
No code, prompt or credential is read back beyond the log fields.
"""

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from math import ceil
from pathlib import Path
from statistics import median


def parse_time(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def percentiles(values):
    values = sorted(values)
    if not values:
        return {"count": 0, "p50_ms": None, "p95_ms": None, "max_ms": None}
    return {"count": len(values), "p50_ms": round(median(values), 1),
            "p95_ms": round(values[ceil(0.95 * len(values)) - 1], 1),
            "max_ms": round(values[-1], 1)}


def load(paths, since_minutes=None):
    cutoff = None
    if since_minutes is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=since_minutes)
    rows = []
    undated = 0
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or "elapsed_ms" not in row or "source" not in row:
                continue
            stamp = parse_time(row.get("ts"))
            if cutoff is not None:
                if stamp is None:
                    undated += 1
                    continue
                if stamp < cutoff:
                    continue
            rows.append(row)
    return rows, undated


def summarise(rows, budget_per_day=None):
    cloud = [row for row in rows if row.get("source") != "local"]
    fallback = [row for row in rows if row.get("source") == "local"]
    reasons = Counter(row.get("fallback_reason") or "none" for row in fallback)
    sources = Counter(row.get("source") for row in rows)
    per_day = Counter()
    for row in rows:
        stamp = parse_time(row.get("ts"))
        if stamp is not None:
            per_day[stamp.astimezone(timezone.utc).date().isoformat()] += 1
    report = {
        "calls": len(rows),
        "cloud_calls": len(cloud),
        "fallback_calls": len(fallback),
        "cloud_rate": round(len(cloud) / len(rows), 3) if rows else None,
        "fallback_rate": round(len(fallback) / len(rows), 3) if rows else None,
        "fallback_reasons": dict(reasons),
        "sources": dict(sources),
        "latency_all": percentiles([float(row["elapsed_ms"]) for row in rows]),
        "latency_cloud": percentiles([float(row["elapsed_ms"]) for row in cloud]),
        "latency_fallback": percentiles([float(row["elapsed_ms"]) for row in fallback]),
        "calls_per_day": dict(sorted(per_day.items())),
        "budget_per_day": budget_per_day,
        "budget_exceeded": sorted(day for day, count in per_day.items()
                                  if budget_per_day is not None and count > budget_per_day),
    }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="汇总 AI 提示日志的命中率、回退原因与耗时")
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--since-minutes", type=int, help="只看最近 N 分钟（需要日志含 ts 字段）")
    parser.add_argument("--budget-per-day", type=int, help="单日调用数警戒线；超过则以退出码 1 失败")
    parser.add_argument("--json", type=Path, help="写出机器可读汇总")
    args = parser.parse_args(argv)
    rows, undated = load(args.logs, args.since_minutes)
    if not rows:
        print("没有可解析的提示日志行。检查 AI_LOG_FILE 是否启用并包含请求记录。", file=__import__("sys").stderr)
        return 2
    report = summarise(rows, args.budget_per_day)
    report["undated_rows_skipped"] = undated
    print(f"调用 {report['calls']} 次：云端 {report['cloud_calls']}，回退 {report['fallback_calls']}")
    print(f"命中率 {report['cloud_rate']}，回退率 {report['fallback_rate']}")
    print(f"全部耗时 P50/P95/最大：{report['latency_all']['p50_ms']}/{report['latency_all']['p95_ms']}/{report['latency_all']['max_ms']} ms")
    print(f"云端耗时 P50/P95/最大：{report['latency_cloud']['p50_ms']}/{report['latency_cloud']['p95_ms']}/{report['latency_cloud']['max_ms']} ms")
    if report["fallback_reasons"]:
        print("回退原因：" + "，".join(f"{name} {count}" for name, count in
                                    sorted(report["fallback_reasons"].items(), key=lambda item: -item[1])))
    if report["calls_per_day"]:
        print("每日调用：" + "，".join(f"{day} {count}" for day, count in report["calls_per_day"].items()))
    if args.since_minutes is not None and undated:
        print(f"注意：{undated} 行没有 ts 字段，无法按时间窗过滤，已跳过。")
    if report["budget_exceeded"]:
        print(f"预算告警：{', '.join(report['budget_exceeded'])} 超过每日 {args.budget_per_day} 次。")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if report["budget_exceeded"] else 0


if __name__ == "__main__":
    raise SystemExit(main())