"""Dedicated metadata / explicitly authorized Luogu content pack importer."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import question_bank as bank

CONTENT_FIELDS = {'statement', 'samples', 'inputFormat', 'outputFormat', 'background', 'hint', 'translations', 'reference_code', 'cases'}
REMOTE_FIELDS = {'pid', 'languages', 'language_caveat', 'statement_available', 'content_authorized', 'difficulty_original', 'main_category', 'official_tags', 'limits', 'selection_evidence'}


def validate_pack(pack):
    if not isinstance(pack, dict) or type(pack.get('schema_version')) is not int or pack['schema_version'] != 2 or pack.get('pack_kind') != 'remote':
        raise bank.BankError('expected schema_version 2 remote pack')
    bank._text(pack.get('pack_id'), 'pack_id', 100)
    bank._text(pack.get('version'), 'version', 100)
    specs = pack.get('problems')
    if not isinstance(specs, list) or not 1 <= len(specs) <= 200:
        raise bank.BankError('pack must contain 1 to 200 problems')
    seen = set()
    for spec in specs:
        if not isinstance(spec, dict) or spec.get('engine') != 'luogu_remote':
            raise bank.BankError('expected luogu_remote problem')
        remote = spec.get('remote')
        if not isinstance(remote, dict) or not re.fullmatch(r'[PB][1-9][0-9]{2,6}', str(remote.get('pid', ''))):
            raise bank.BankError('invalid official PID')
        if set(remote) - REMOTE_FIELDS:
            raise bank.BankError('unexpected remote metadata field')
        if type(remote.get('statement_available')) is not bool:
            raise bank.BankError('statement_available must be boolean')
        if spec.get('id') != 'luogu_' + remote['pid'] or spec['id'] in seen:
            raise bank.BankError('invalid or duplicate problem ID')
        seen.add(spec['id'])
        for key in bank.PUBLIC_FIELDS:
            if key not in spec:
                raise bank.BankError('missing problem field: ' + key)
        for key in ('title', 'version', 'description', 'learning_goal', 'starter_code'):
            bank._text(spec[key], key)
        if spec['signature'] != '' or spec['parameters'] != []:
            raise bank.BankError('remote problems use stdin/stdout, not local signatures')
        if spec['difficulty'] not in ('easy', 'medium') or not isinstance(spec['tags'], list) or not spec['tags']:
            raise bank.BankError('invalid difficulty or category')
        for tag in spec['tags']:
            bank._text(tag, 'tag', 100)
        for key in ('name', 'url', 'revision', 'license', 'attribution', 'adaptation'):
            bank._text(spec['source'].get(key), 'source.' + key)
        if not re.fullmatch(r'[0-9a-f]{64}', spec['source']['revision']):
            raise bank.BankError('source revision must be official snapshot SHA256')
        if spec['source']['url'] != 'https://www.luogu.com.cn/problem/' + remote['pid']:
            raise bank.BankError('source URL must match official PID')
        content = bool(CONTENT_FIELDS.intersection(spec)) or remote.get('statement_available') is not False
        if content and os.environ.get('LUOGU_CONTENT_AUTHORIZED') != '1':
            raise bank.BankError('content import requires explicit LUOGU_CONTENT_AUTHORIZED=1 authorization')
        if not content and spec['description'] != '题面待授权同步。请通过官方题目链接阅读；本目录仅提供题号、标题与分类元数据。':
            raise bank.BankError('metadata description must not mirror problem content')
        if not isinstance(remote.get('languages'), list) or not remote['languages']:
            raise bank.BankError('remote language configuration required')
    return pack


def import_pack(path, db=None):
    pack = validate_pack(bank.read_pack(path))
    bundled = {s['id'] for s in bank._bundled()}
    if any(s['id'] in bundled for s in pack['problems']):
        raise bank.BankError('problem id collides with bundled problem')
    target = bank._db_path(db)
    target.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(target)) as conn:
        try:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('CREATE TABLE IF NOT EXISTS problems (id TEXT PRIMARY KEY, pack_id TEXT NOT NULL, version TEXT NOT NULL, spec TEXT NOT NULL)')
            for spec in pack['problems']:
                conn.execute('INSERT INTO problems VALUES (?, ?, ?, ?)', (spec['id'], pack['pack_id'], pack['version'], json.dumps(spec, ensure_ascii=False)))
            conn.commit()
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise bank.BankError('problem id already imported') from exc
    return {'pack_id': pack['pack_id'], 'imported': len(pack['problems'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['validate', 'preview', 'import'])
    parser.add_argument('path')
    parser.add_argument('--db')
    args = parser.parse_args(argv)
    try:
        if args.command == 'import':
            result = import_pack(args.path, args.db)
        else:
            pack = validate_pack(bank.read_pack(args.path))
            result = {'pack_id': pack['pack_id'], 'count': len(pack['problems'])}
            if args.command == 'preview':
                result['items'] = [bank.public_problem(s) for s in pack['problems']]
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (bank.BankError, OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
        parser.exit(1, f'luogu bank: {exc}\n')


if __name__ == '__main__':
    main()
