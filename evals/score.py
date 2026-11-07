"""Summarise rubric reviews from evaluation reports and flag anything that contradicts the product rules."""

import argparse
import json
from pathlib import Path
from statistics import median

import agentarts


FIELDS = ("evidence_ok", "actionable", "answer_leaked")
MAX_HINT_LENGTH = 240  # mirrors the client check in agentarts.get_hint
SIDES = ("local", "endpoint")
SIDE_LABELS = {"local": "本地", "cloud": "云端"}


def load(path):
    """Read one report file and reject anything that is not shaped like evals.run output."""
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(report, dict) or not isinstance(report.get("summary"), dict):
        raise ValueError("报告缺少 summary 对象")
    if not isinstance(report.get("records"), list) or not report["records"]:
        raise ValueError("报告缺少非空 records 数组")
    return report


def positions(report):
    """Yield (record, level row, side, entry) for every hint the report carries."""
    for record in report["records"]:
        if not isinstance(record, dict) or not isinstance(record.get("levels"), list):
            raise ValueError("records 中每一项都需要带 levels 数组")
        for row in record["levels"]:
            if not isinstance(row, dict) or not isinstance(row.get("local"), dict):
                raise ValueError(f"样本 {record['sample_id']} 的某一级别缺少本地提示")
            yield record, row, "local", row["local"]
            if isinstance(row.get("endpoint"), dict):
                yield record, row, "endpoint", row["endpoint"]


def review_of(entry):
    review = entry.get("review")
    return review if isinstance(review, dict) else {}


def is_reviewed(entry):
    review = review_of(entry)
    return bool(review) and all(review.get(field) is not None for field in FIELDS)


def tally(entries):
    """Count true verdicts per rubric field, each against the rows that scored that field."""
    scored = [entry for entry in entries if review_of(entry)]
    counts = {"rows": len(entries), "reviewed": sum(1 for entry in entries if is_reviewed(entry))}
    for field in FIELDS:
        verdicts = [review_of(entry).get(field) for entry in scored]
        counts[field] = sum(1 for verdict in verdicts if verdict is True)
        counts[field + "_scored"] = sum(1 for verdict in verdicts if verdict is not None)
    return counts


def outcomes(report):
    rows = [row["endpoint"] for record in report["records"] for row in record["levels"]
            if isinstance(row.get("endpoint"), dict)]
    return {outcome: sum(1 for row in rows if row.get("outcome") == outcome)
            for outcome in ("cloud", "fallback", "error")}


def cloud_pairs(report):
    """Level rows where the endpoint returned a real cloud hint: the only rows usable for quality comparison."""
    return [row for record in report["records"] for row in record["levels"]
            if isinstance(row.get("endpoint"), dict) and row["endpoint"].get("outcome") == "cloud"]


def pending_positions(report):
    """Positions a reviewer still has to grade, ignoring errors and fallbacks that repeat the local text."""
    pending = []
    for record, row, side, entry in positions(report):
        if side == "endpoint" and entry.get("outcome") != "cloud":
            continue
        if not is_reviewed(entry):
            pending.append([record["sample_id"], row["level"], side, entry.get("hint") or ""])
    return pending


def failed_case_ids(record):
    return {case.get("id") for case in record.get("failed_cases", []) if isinstance(case, dict)}


def check_row(record, row, side, entry, issues):
    """Apply the rules the product itself enforces, so a report cannot quietly contradict them."""
    label = f"{record['sample_id']} 第 {row.get('level')} 级"
    hint = entry.get("hint")
    if side == "endpoint":
        outcome = entry.get("outcome")
        if outcome == "error":
            if hint is not None:
                issues.append(f"{label}：错误行不应带提示文本")
            return
        if outcome == "fallback":
            if hint != row["local"].get("hint"):
                issues.append(f"{label}：回退提示与同级本地提示不一致")
            return
        if outcome != "cloud":
            issues.append(f"{label}：未知的接口结果 {outcome}")
            return
        if not entry.get("request_id"):
            issues.append(f"{label}：云端命中缺少 request_id，无法与控制台执行记录核对")
    if hint is None:
        issues.append(f"{label}：缺少提示文本")
        return
    if entry.get("case_id") not in failed_case_ids(record):
        issues.append(f"{label}：case_id {entry.get('case_id')} 不在失败用例里")
    if side != "endpoint":
        return
    if not hint.strip() or len(hint.strip()) > MAX_HINT_LENGTH or len(hint.strip().splitlines()) != 1:
        issues.append(f"{label}：云端提示不是单行 240 字以内，客户端本应拒绝")
    if agentarts._SOLUTION.search(hint):
        issues.append(f"{label}：云端提示含可复制答案，客户端本应拒绝")
    elif review_of(entry).get("answer_leaked") is True:
        issues.append(f"{label}：人工判为泄露但机器规则未拦截，需要补 agentarts._SOLUTION")


def check_summary(report, result):
    """Recount from the rows and compare with the numbers the report itself claims."""
    summary = report["summary"]
    levels = [row for record in report["records"] for row in record["levels"]]
    expected = {"local_rows": len(levels)}
    for outcome, count in result["outcomes"].items():
        expected[outcome + "_rows"] = count
    for key, value in expected.items():
        if key in summary and summary[key] != value:
            result["issues"].append(f"summary.{key}={summary[key]}，逐条统计为 {value}")
    claimed = summary.get("local_review")
    if isinstance(claimed, dict):
        for field in FIELDS:
            if field in claimed and claimed[field] != result["local"][field]:
                result["issues"].append(
                    f"summary.local_review.{field}={claimed[field]}，逐条统计为 {result['local'][field]}")
    timings = [row["local"]["elapsed_ms"] for row in levels if "elapsed_ms" in row["local"]]
    if "local_median_ms" in summary and len(timings) == len(levels):
        if round(median(timings), 3) != summary["local_median_ms"]:
            result["issues"].append("summary.local_median_ms 与逐条耗时中位数不一致")


def score_report(path):
    report = load(path)
    result = {"report": str(path), "mode": report.get("mode", "未知"), "note": report.get("note", "未标注来源"),
              "issues": [], "drift": [], "local_note": "", "outcomes": outcomes(report)}
    entries = {side: [] for side in SIDES}
    for record, row, side, entry in positions(report):
        entries[side].append(entry)
        check_row(record, row, side, entry, result["issues"])
    result["local"] = tally(entries["local"])
    result["endpoint"] = tally(entries["endpoint"])
    result["pending"] = pending_positions(report)
    if entries["endpoint"]:
        paired = cloud_pairs(report)
        result["paired"] = {"cloud_pairs": len(paired),
                            "local": tally([row["local"] for row in paired]),
                            "cloud": tally([row["endpoint"] for row in paired])}
    check_summary(report, result)
    return result


def local_hints(report):
    return {(record["sample_id"], row["level"]): row["local"].get("hint")
            for record in report["records"] for row in record["levels"]}


def compare_local(reference, other):
    """Reports from the same grader must carry identical local text; drift means one file is stale."""
    left, right = local_hints(reference), local_hints(other)
    return [[key, left.get(key, "（缺该位置）"), right.get(key, "（缺该位置）")]
            for key in sorted(set(left) | set(right), key=str) if left.get(key) != right.get(key)]


def add_drift_check(results, reference_path):
    """Local text must match the baseline report, or the two sides of a pair are no longer comparable."""
    reference = load(reference_path)
    graded = tally([row["local"] for record in reference["records"] for row in record["levels"]])
    for result in results:
        result["drift"] = compare_local(reference, load(Path(result["report"])))
        if result["drift"]:
            result["issues"].append(f"本地侧提示与基准 {reference_path} 有 {len(result['drift'])} 处不同，"
                                    "样本集或判题器已变更，两侧不再可比")
        elif graded["reviewed"] == graded["rows"] == result["local"]["rows"]:
            result["local_note"] = f"本地侧逐条与基准一致，可沿用基准报告已打的 {graded['reviewed']} 条打分。"


def render(result, limit):
    print(f"=== {result['report']} ===")
    print(f"模式 {result['mode']} · 来源 {result['note']}")
    if "模拟" in result["note"]:
        print("        注：模拟数据不计入云端证据，也不参与下面的质量比较。")
    local = result["local"]
    scores = " · ".join(f"{field} {local[field]}/{local[field + '_scored']}" for field in FIELDS)
    print(f"本地侧 {local['rows']} 条 · 已复核 {local['reviewed']} · {scores}")
    cloud = result["endpoint"]
    if cloud["rows"]:
        reached = result["outcomes"]
        print(f"接口侧 {cloud['rows']} 次调用 · 命中 {reached['cloud']} · 回退 {reached['fallback']} "
              f"· 错误 {reached['error']}")
        if cloud["reviewed"]:
            scores = " · ".join(f"{field} {cloud[field]}/{cloud[field + '_scored']}" for field in FIELDS)
            print(f"        云端打分 · {scores}")
        paired = result["paired"]
        if paired["cloud_pairs"]:
            both = "，".join(f"{SIDE_LABELS[side]} " + " / ".join(
                f"{field} {paired[side][field]}/{paired[side][field + '_scored']}" for field in FIELDS)
                for side in ("local", "cloud"))
            print(f"有效配对 {paired['cloud_pairs']} 对（质量比较只用这些）：{both}")
    if result["drift"]:
        print(f"本地侧漂移 {len(result['drift'])} 处：")
        for (sample_id, level), before, after in result["drift"][:limit]:
            print(f"  {sample_id} 第 {level} 级：基准「{before[:20]}」→ 本报告「{after[:20]}」")
    if result["pending"]:
        print(f"待复核 {len(result['pending'])} 条：")
        if result["local_note"]:
            print(f"        {result['local_note']}")
        for sample_id, level, side, hint in result["pending"][:limit]:
            print(f"  {sample_id} 第 {level} 级 [{side}] {hint[:38] or '（无文本）'}")
        if len(result["pending"]) > limit:
            print(f"  …其余 {len(result['pending']) - limit} 条，用 --limit 展开")
    else:
        print("待复核 无")
    for issue in result["issues"]:
        print(f"[问题] {issue}")
    verdict = "[通过] 逐条与产品规则一致" if not result["issues"] else f"[不符] {len(result['issues'])} 项不一致"
    print(verdict + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reports", nargs="+", type=Path, help="evals.run 产出的报告文件")
    parser.add_argument("--against", type=Path, help="用这份基准报告核对本地侧文本是否漂移")
    parser.add_argument("--json", type=Path, help="把统计结果写成机器可读的 JSON，供提交材料引用")
    parser.add_argument("--limit", type=int, default=8, help="待复核清单最多列几条，默认 8")
    parser.add_argument("--require-complete", action="store_true", help="仍有待复核位置时以非零退出码失败")
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit 至少为 1")

    results = []
    try:
        for path in args.reports:
            results.append(score_report(path))
        if args.against:
            add_drift_check(results, args.against)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(f"[失败] 报告结构不符：{error}")
        return 2

    for result in results:
        render(result, args.limit)
    issues = [issue for result in results for issue in result["issues"]]
    pending_total = sum(len(result["pending"]) for result in results)
    if args.json:
        body = json.dumps({"reports": results}, ensure_ascii=False, indent=2) + "\n"
        args.json.write_text(body, encoding="utf-8")
        print(f"统计结果已写入 {args.json}")
    if issues:
        print(f"{len(issues)} 项与产品规则或基准报告不一致，请先修复采集或校验逻辑。")
        return 1
    if pending_total and args.require_complete:
        print(f"{pending_total} 个位置尚未复核，--require-complete 要求全部打分。")
        return 1
    print(f"{len(results)} 份报告通过一致性检查；待复核 {pending_total} 条。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
