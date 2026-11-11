"""Check a small-batch AgentArts retest report against the fixed failure samples."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAMPLES = ROOT / 'evals/agentarts-102056-retest-samples.json'
LEVELS = (1, 2, 3)


def expected_positions(path):
    samples = json.loads(Path(path).read_text(encoding='utf-8'))
    return {(str(sample['id']), level) for sample in samples for level in LEVELS}


def collect(report, expected):
    rows = []
    for record in report.get('records', []):
        sample_id = str(record.get('sample_id'))
        levels = {int(row.get('level')): row for row in record.get('levels', [])}
        for level in LEVELS:
            if (sample_id, level) not in expected:
                continue
            endpoint = (levels.get(level) or {}).get('endpoint') or {}
            rows.append({
                'sample_id': sample_id, 'level': level,
                'outcome': endpoint.get('outcome') or 'missing',
                'fallback_reason': endpoint.get('fallback_reason'),
                'execution_id': endpoint.get('execution_id'),
                'cloud_error_code': endpoint.get('cloud_error_code'),
                'failed_node_id': endpoint.get('failed_node_id'),
                'elapsed_ms': endpoint.get('elapsed_ms'),
            })
    return rows


def summarise(rows, expected):
    seen = {(row['sample_id'], row['level']) for row in rows}
    cloud = sum(row['outcome'] == 'cloud' for row in rows)
    return {
        'expected': len(expected), 'rows': len(rows),
        'missing': sorted([list(key) for key in expected - seen]),
        'cloud': cloud,
        'fallback': sum(row['outcome'] == 'fallback' for row in rows),
        'error': sum(row['outcome'] == 'error' for row in rows),
        'passed': len(seen) == len(expected) and cloud == len(expected),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--samples', type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        expected = expected_positions(args.samples)
    except (OSError, ValueError, KeyError, TypeError):
        print('无法读取复测报告或样本文件。')
        return 2
    rows = collect(report, expected)
    summary = summarise(rows, expected)
    print('\t'.join(('样本', '等级', '结果', '回退原因', 'execution_id', '错误码', '失败节点', '耗时ms')))
    for row in rows:
        print('\t'.join(str(row[key] or '') for key in
                        ('sample_id', 'level', 'outcome', 'fallback_reason',
                         'execution_id', 'cloud_error_code', 'failed_node_id', 'elapsed_ms')))
    print(f"云端 {summary['cloud']}/{summary['expected']}，回退 {summary['fallback']}，错误 {summary['error']}")
    if summary['missing']:
        print('缺少位置: ' + ', '.join(f'{sample} L{level}' for sample, level in summary['missing']))
    if args.json:
        args.json.write_text(json.dumps({'rows': rows, 'summary': summary},
                                        ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('结论: PASS' if summary['passed'] else '结论: FAIL')
    return 0 if summary['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())