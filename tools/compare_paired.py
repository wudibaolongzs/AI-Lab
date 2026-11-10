"""Compare two paired reports before and after a prompt revision.

Reads only reviewed cloud positions, keyed by (sample, level), and reports
which rubric verdicts were fixed, regressed, still failing or never reviewed.
It never calls the cloud.
"""

import argparse
import json
from pathlib import Path

FIELDS = ("evidence_ok", "actionable", "answer_leaked")


def cloud_reviews(report):
    rows = {}
    for record in report.get("records", []):
        sample = str(record.get("sample_id"))
        for row in record.get("levels", []):
            endpoint = row.get("endpoint") or {}
            if endpoint.get("outcome") != "cloud":
                continue
            key = (sample, int(row.get("level")))
            rows[key] = endpoint.get("review") or {}
    return rows


def compare(before, after):
    old = cloud_reviews(before)
    new = cloud_reviews(after)
    keys = sorted(set(old) & set(new))
    summary = {field: {"fixed": 0, "regressed": 0, "still_failed": 0,
                       "unreviewed": 0, "passed": 0} for field in FIELDS}
    entries = []
    for key in keys:
        for field in FIELDS:
            previous = old[key].get(field)
            current = new[key].get(field)
            if current is None:
                change = "unreviewed"
            elif current is True and previous is False:
                change = "fixed"
            elif current is False and previous is True:
                change = "regressed"
            elif current is False:
                change = "still_failed"
            elif current is True:
                change = "passed"
            else:
                change = "unreviewed"
            summary[field][change] += 1
            if change in ("fixed", "regressed", "still_failed"):
                entries.append({"sample_id": key[0], "level": key[1],
                                "field": field, "before": previous,
                                "after": current, "change": change})
    return {
        "compared_positions": len(keys),
        "only_in_before": sorted(set(old) - set(new)),
        "only_in_after": sorted(set(new) - set(old)),
        "summary": summary,
        "entries": entries,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="比较提示词修订前后的云端评分")
    parser.add_argument("before", type=Path, help="修订前的配对报告")
    parser.add_argument("after", type=Path, help="修订后重新采集并复核的报告")
    parser.add_argument("--json", type=Path, help="写出机器可读比较结果")
    args = parser.parse_args(argv)
    try:
        before = json.loads(args.before.read_text(encoding="utf-8"))
        after = json.loads(args.after.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        parser.exit(2, f"报告读取失败：{error}\n")
    report = compare(before, after)
    if not report["compared_positions"]:
        parser.exit(2, "没有可比较的云端位置：两份报告都需包含 outcome=cloud 且带 review 的记录。\n")
    for field in FIELDS:
        counts = report["summary"][field]
        print(f"{field}: 修复 {counts['fixed']}，回归 {counts['regressed']}，"
              f"仍失败 {counts['still_failed']}，通过 {counts['passed']}，未复核 {counts['unreviewed']}")
    for entry in report["entries"]:
        state = {"fixed": "已修复", "regressed": "回归", "still_failed": "仍失败"}[entry["change"]]
        print(f"  {entry['sample_id']} 第 {entry['level']} 级 {entry['field']}：{state}"
              f"（{entry['before']} → {entry['after']}）")
    if report["only_in_before"]:
        print("仅旧报告包含：" + "，".join(f"{s}-L{l}" for s, l in report["only_in_before"]))
    if report["only_in_after"]:
        print("仅新报告包含：" + "，".join(f"{s}-L{l}" for s, l in report["only_in_after"]))
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if any(counts["regressed"] for counts in report["summary"].values()):
        return 1
    if any(counts["unreviewed"] for counts in report["summary"].values()):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())