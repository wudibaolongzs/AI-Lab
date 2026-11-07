"""Export blank human-review worksheets and import explicit verdicts, without cloud calls."""
import argparse
import copy
import csv
import json
import unicodedata
from pathlib import Path

from evals.score import FIELDS, load, positions

COLUMNS = ("sample_id", "level", "side", "case_id", "hint", *FIELDS)


def csv_cell(value):
    """Reversibly quote spreadsheet formula prefixes and literal apostrophes."""
    value = str(value)
    if value and (value[0] in "=+-@'" or value[0].isspace()
                  or unicodedata.category(value[0]).startswith("C")):
        return "'" + value
    return value


def raw_cell(value):
    return value[1:] if value and value.startswith("'") else value


def eligible(report):
    entries = {}
    for record, row, side, entry in positions(report):
        if side == "endpoint" and entry.get("outcome") != "cloud":
            continue
        key = (str(record["sample_id"]), str(row["level"]), side)
        if key in entries:
            raise ValueError(f"duplicate report key: {key}")
        entries[key] = entry
    return entries


def export_csv(report, output):
    with Path(output).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        for key, entry in eligible(report).items():
            writer.writerow({field: csv_cell(value) for field, value in
                             dict(zip(COLUMNS[:3], key), case_id=entry.get("case_id", ""),
                                  hint=entry.get("hint", "")).items()})


def parse_bool(value):
    if value == "":
        return None
    if value not in ("true", "false"):
        raise ValueError("verdict must be blank, true or false")
    return value == "true"


def import_csv(report, worksheet, baseline=None):
    result = copy.deepcopy(report)
    expected = eligible(result)
    seen = set()
    with Path(worksheet).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError("unexpected CSV columns")
        for row in reader:
            for field in COLUMNS[:5]:
                row[field] = raw_cell(row[field])
            key = tuple(row[field] for field in COLUMNS[:3])
            if key in seen or key not in expected:
                raise ValueError(f"duplicate or unknown CSV key: {key}")
            seen.add(key)
            entry = expected[key]
            if row["hint"] != entry.get("hint", "") or row["case_id"] != entry.get("case_id", ""):
                raise ValueError(f"hint or case changed: {key}")
            entry["review"] = {field: parse_bool(row[field]) for field in FIELDS}
    if seen != set(expected):
        raise ValueError("missing CSV entries")
    if baseline is not None:
        source = eligible(baseline)
        for key, entry in expected.items():
            old = source.get(key, {})
            if (key[2] == "local" and old.get("hint") == entry.get("hint")
                    and old.get("case_id") == entry.get("case_id")):
                for field in FIELDS:
                    verdict = (old.get("review") or {}).get(field)
                    if entry["review"][field] is None and type(verdict) is bool:
                        entry["review"][field] = verdict
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "import"))
    parser.add_argument("report", type=Path)
    parser.add_argument("worksheet", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reuse-local-from", type=Path)
    args = parser.parse_args(argv)
    try:
        report = load(args.report)
        if args.action == "export":
            if args.worksheet.resolve() == args.report.resolve():
                raise ValueError("worksheet cannot overwrite report")
            export_csv(report, args.worksheet)
        else:
            if not args.output or args.output.resolve() in {args.report.resolve(), args.worksheet.resolve()}:
                raise ValueError("--output must be a separate file")
            baseline = load(args.reuse_local_from) if args.reuse_local_from else None
            if args.reuse_local_from and args.output.resolve() == args.reuse_local_from.resolve():
                raise ValueError("output cannot overwrite baseline")
            result = import_csv(report, args.worksheet, baseline)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"review failed: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
