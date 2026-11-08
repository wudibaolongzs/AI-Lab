"""Generate an operator-owned classroom credential file, never print tokens."""
import argparse
import json
import os
from pathlib import Path
import secrets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--class-id', required=True)
    parser.add_argument('--students', required=True, nargs='+', help='Unique student aliases')
    args = parser.parse_args()
    if not args.class_id.strip() or len(set(args.students)) != len(args.students) or any(not s.strip() for s in args.students):
        parser.error('class and student aliases must be nonempty and unique')
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if output == root or root in output.parents:
        parser.error('credential file must be outside the repository')
    config = {'classes': {args.class_id: {'teacher_token': secrets.token_urlsafe(32), 'students': {s: secrets.token_urlsafe(32) for s in args.students}}}}
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as stream:
        json.dump(config, stream, ensure_ascii=False, indent=2)
    print('Credential file created. Restrict its Windows ACL to the operator account; distribute each credential privately.')


if __name__ == '__main__':
    main()
