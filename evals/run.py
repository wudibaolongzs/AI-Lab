"""Collect local hints and optionally pair them with a running AI-Lab service."""

import argparse
from collections import Counter
import http.client
import json
from pathlib import Path
from statistics import median
from math import ceil
from time import perf_counter

from exercise import check_submission


SAMPLES_PATH = Path(__file__).with_name("samples.json")
LEVELS = (1, 2, 3)
REVIEW = {"evidence_ok": None, "actionable": None, "answer_leaked": None}


def elapsed_ms(start):
    return round((perf_counter() - start) * 1000, 3)


def request_hint(port, code, level, exercise_id="average", timeout=15):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    body = json.dumps({"exercise_id": exercise_id, "code": code, "level": level})
    start = perf_counter()
    try:
        connection.request("POST", "/api/hint", body, {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status != 200:
            outcome = {"outcome": "error", "http_status": response.status}
        else:
            data = json.loads(response.read())
            if (
                not isinstance(data, dict)
                or data.get("source") not in ("agentarts", "tencent", "deepseek", "local")
                or any(not isinstance(data.get(key), str) or not data[key].strip()
                       for key in ("hint", "case_id", "request_id"))
            ):
                raise ValueError("invalid hint response")
            outcome = {key: data[key] for key in ("hint", "case_id", "source", "request_id")}
            outcome["outcome"] = "cloud" if data["source"] in ("agentarts", "tencent", "deepseek") else "fallback"
            if outcome["outcome"] == "cloud":
                outcome["review"] = REVIEW.copy()
    except (OSError, http.client.HTTPException, ValueError) as error:
        outcome = {"outcome": "error", "error_kind": type(error).__name__}
    finally:
        connection.close()
    outcome["elapsed_ms"] = elapsed_ms(start)
    return outcome


def collect(samples, port, timeout=15):
    records = []
    for sample in samples:
        exercise_id = sample.get("exercise", "average")
        levels = []
        for level in LEVELS:
            start = perf_counter()
            result = check_submission(sample["code"], exercise_id)
            local_ms = elapsed_ms(start)
            failed = [case for case in result["cases"] if case["status"] != "passed"]
            if (
                result["status"] != "failed"
                or not failed
                or failed[0]["id"] != sample["case_id"]
                or result["diagnosis"]["kind"] != sample["diagnosis_kind"]
                or len(result["hints"]) != len(LEVELS)
            ):
                raise ValueError(f"fixture no longer matches the grader: {sample['id']}")
            row = {
                "level": level,
                "local": {"source": "local", "hint": result["hints"][level - 1],
                          "case_id": failed[0]["id"], "elapsed_ms": local_ms,
                          "review": REVIEW.copy()},
            }
            if port is not None:
                row["endpoint"] = request_hint(port, sample["code"], level, exercise_id, timeout)
            levels.append(row)
        records.append({
            "sample_id": sample["id"], "exercise": exercise_id,
            "category": sample["category"], "focus": sample["focus"],
            "diagnosis": result["diagnosis"], "failed_cases": failed, "levels": levels,
        })
    return records


def latency_stats(timings):
    """Milliseconds; P95 uses nearest rank ceil(.95*n), without interpolation."""
    values = sorted(timings)
    if not values:
        return {"median_ms": None, "p95_ms": None, "max_ms": None}
    return {"median_ms": round(median(values), 3),
            "p95_ms": round(values[ceil(.95 * len(values)) - 1], 3),
            "max_ms": round(values[-1], 3)}


def summarize(records, paired):
    levels = [row for record in records for row in record["levels"]]
    summary = {
        "samples": len(records),
        "local_rows": len(levels),
    }
    summary.update({"local_" + key: value for key, value in
                    latency_stats(row["local"]["elapsed_ms"] for row in levels).items()})
    if paired:
        outcomes = Counter(row["endpoint"]["outcome"] for row in levels)
        summary["endpoint_attempts"] = len(levels)
        for outcome in ("cloud", "fallback", "error"):
            summary[outcome + "_rows"] = outcomes[outcome]
            timings = [row["endpoint"]["elapsed_ms"] for row in levels
                       if row["endpoint"]["outcome"] == outcome]
            summary.update({outcome + "_" + key: value for key, value in latency_stats(timings).items()})
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", type=Path, default=SAMPLES_PATH, help="Independent sample set; defaults to the original 24 samples.")
    parser.add_argument("--compare-port", type=int, help="Also call the local /api/hint endpoint.")
    parser.add_argument("--timeout", type=float, default=15.0,
                        help="Per-request wait for the hint endpoint; raise it above the backend AI_TIMEOUT.")
    parser.add_argument("--note", help="Provenance written to the report, e.g. that the endpoint is a mock.")
    args = parser.parse_args()
    if args.compare_port is not None and not 1 <= args.compare_port <= 65535:
        parser.error("--compare-port must be 1–65535")
    if not 0.5 <= args.timeout <= 300:
        parser.error("--timeout must be 0.5–300 seconds")
    if args.note and args.compare_port is None:
        parser.error("--note 只在配对采集时使用")
    samples = json.loads(args.samples.read_text(encoding="utf-8"))
    if not isinstance(samples, list) or not samples:
        parser.error("sample set must be a non-empty array")
    records = collect(samples, args.compare_port, args.timeout)
    report = {
        "mode": "endpoint-comparison" if args.compare_port is not None else "local-only",
        "note": args.note or "未标注来源",
        "summary": summarize(records, args.compare_port is not None),
        "records": records,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
