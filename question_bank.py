"""Versioned, offline question packs and transactional local imports."""
import argparse
import copy
from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sqlite3

ROOT = Path(__file__).resolve().parent
BUNDLED_PATHS = (ROOT / 'data/builtin.json', ROOT / 'data/exercism-foundations.json', *(ROOT / 'data/luogu').glob('pack-*.json'))
PUBLIC_FIELDS = ('id', 'version', 'title', 'description', 'learning_goal', 'tags',
                 'difficulty', 'source', 'signature', 'parameters', 'return_type',
                 'starter_code', 'engine')
MAX_BYTES = 2 * 1024 * 1024


class BankError(ValueError):
    """An invalid pack; no changes have been applied."""


def _db_path(db=None):
    return Path(db or os.environ.get('AI_QUESTIONBANK_DB') or ROOT / 'data/question-bank.sqlite3')


def _text(value, label, limit=12000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise BankError(f'{label}: expected nonempty string up to {limit} characters')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise BankError(f'{label}: invalid UTF-8 string') from exc


def _bounded(value, depth=0):
    if depth > 4:
        raise BankError('case value nesting exceeds limit')
    if value is None or type(value) is bool:
        return
    if type(value) in (int, float):
        if abs(value) > 1e12 or not math.isfinite(value):
            raise BankError('case number outside finite bounds')
    elif isinstance(value, str):
        if len(value) > 4000:
            raise BankError('case string exceeds limit')
        try:
            value.encode('utf-8')
        except UnicodeError as exc:
            raise BankError('case string is not valid UTF-8') from exc
    elif isinstance(value, list):
        if len(value) > 256:
            raise BankError('case list exceeds limit')
        for item in value:
            _bounded(item, depth + 1)
    else:
        raise BankError('case values must be bounded JSON primitives or lists')


def _spec(spec, trusted=False, execute=True):
    if not isinstance(spec, dict):
        raise BankError('problem must be an object')
    for key in PUBLIC_FIELDS + ('reference_code',):
        if key not in spec:
            raise BankError(f'missing problem field: {key}')
    for key in ('id', 'version', 'title', 'description', 'learning_goal', 'signature',
                'return_type', 'starter_code', 'reference_code'):
        _text(spec[key], key, 4000 if key.endswith('_code') else 12000)
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_-]{0,99}', spec['id']):
        raise BankError('invalid problem id')
    if spec['difficulty'] not in ('easy', 'medium'):
        raise BankError('difficulty must be easy or medium')
    if not isinstance(spec['tags'], list) or not 1 <= len(spec['tags']) <= 20:
        raise BankError('tags must contain 1 to 20 strings')
    for tag in spec['tags']:
        _text(tag, 'tag', 100)
    source = spec['source']
    if not isinstance(source, dict):
        raise BankError('source must be an object')
    for key in ('name', 'url', 'revision', 'license', 'attribution', 'adaptation'):
        _text(source.get(key), 'source.' + key)
    params = spec['parameters']
    if not isinstance(params, list) or not 1 <= len(params) <= 8:
        raise BankError('parameters must contain 1 to 8 entries')
    names = []
    for param in params:
        if not isinstance(param, dict):
            raise BankError('parameter must be an object')
        _text(param.get('name'), 'parameter name', 100)
        _text(param.get('type'), 'parameter type', 100)
        if not param['name'].isidentifier() or param['name'].startswith('_'):
            raise BankError('invalid parameter name')
        names.append(param['name'])
    if len(set(names)) != len(names):
        raise BankError('duplicate parameter name')
    signature = re.fullmatch(r'def ([A-Za-z][A-Za-z0-9_]*)\(([^()]*)\):', spec['signature'])
    if not signature or [name.strip() for name in signature.group(2).split(',')] != names:
        raise BankError('signature must declare a function with the listed parameters in order')
    cases = spec.get('cases')
    if not isinstance(cases, list) or not 1 <= len(cases) <= 32:
        raise BankError('cases must contain 1 to 32 entries')
    case_ids = set()
    for case in cases:
        if not isinstance(case, dict) or 'expected' not in case:
            raise BankError('case requires id, args and expected')
        _text(case.get('id'), 'case id', 100)
        if case['id'] in case_ids:
            raise BankError('duplicate case id')
        case_ids.add(case['id'])
        if not isinstance(case.get('args'), list) or len(case['args']) != len(params):
            raise BankError('case args must match parameter count')
        _bounded(case['args'])
        _bounded(case['expected'])
    if not isinstance(spec.get('hints'), list) or len(spec['hints']) != 3:
        raise BankError('exactly three hints required')
    for hint in spec['hints']:
        _text(hint, 'hint')
    if 'transfer' in spec:
        transfer = spec['transfer']
        if not isinstance(transfer, dict):
            raise BankError('transfer must be an object')
        for key in ('question_id', 'question'):
            _text(transfer.get(key), 'transfer.' + key)
        answer = transfer.get('answer')
        if type(answer) not in (int, float) or abs(answer) > 1e12 or not math.isfinite(answer):
            raise BankError('transfer answer must be a finite bounded number')
    if spec['engine'] == 'legacy':
        if not trusted:
            raise BankError('legacy engine is reserved for bundled problems')
    elif spec['engine'] == 'bounded_v1':
        from bank_engine import typed
        supported = {'number', 'integer', 'boolean', 'string', 'number_list'}
        if spec['return_type'] not in supported or any(p['type'] not in supported for p in params):
            raise BankError('unsupported parameter or return type')
        for case in cases:
            if not all(typed(value, param['type']) for value, param in zip(case['args'], params)) or not typed(case['expected'], spec['return_type']):
                raise BankError('case value does not match declared type')
        if execute:
            from bank_engine import check
            result = check(spec['reference_code'], spec)
            if result.get('status') != 'passed':
                raise BankError(f"{spec['id']}: reference solution failed")
            if check(spec['starter_code'], spec).get('status') != 'failed':
                raise BankError(f"{spec['id']}: starter must be runnable and fail at least one case")
    else:
        raise BankError('unsupported engine')


def read_pack(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise BankError('pack exceeds 2 MiB')
    try:
        return json.loads(path.read_text(encoding='utf-8'), parse_constant=lambda x: (_ for _ in ()).throw(BankError('nonfinite JSON value')))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise BankError(f'invalid UTF-8 JSON: {exc}') from exc


def validate_pack(pack, *, trusted=False, execute=True):
    if not isinstance(pack, dict) or type(pack.get('schema_version')) is not int or pack['schema_version'] != 1:
        raise BankError('schema_version must be integer 1')
    _text(pack.get('pack_id'), 'pack_id', 100)
    _text(pack.get('version'), 'version', 100)
    problems = pack.get('problems')
    if not isinstance(problems, list) or not 1 <= len(problems) <= 200:
        raise BankError('pack must contain 1 to 200 problems')
    ids = set()
    for spec in problems:
        _spec(spec, trusted=trusted, execute=execute)
        if spec['id'] in ids:
            raise BankError('duplicate problem id in pack: ' + spec['id'])
        ids.add(spec['id'])
    return pack


def _bundled():
    result = []
    for path in BUNDLED_PATHS:
        if Path(path).exists():
            result.extend(read_pack(path)['problems'])
    return result


def _all(db=None):
    result = _bundled()
    path = _db_path(db)
    if path.exists():
        with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as conn:
            result.extend(json.loads(row[0]) for row in conn.execute('SELECT spec FROM problems ORDER BY rowid'))
    return result


def get_problem(problem_id, db=None):
    for spec in _all(db):
        if spec['id'] == problem_id:
            return copy.deepcopy(spec)
    raise KeyError(problem_id)


def public_problem(spec):
    result = {key: copy.deepcopy(spec[key]) for key in PUBLIC_FIELDS}
    result['source'] = {key: copy.deepcopy(spec['source'][key]) for key in
                        ('name', 'url', 'revision', 'license', 'attribution', 'adaptation')}
    if spec.get('engine') == 'luogu_remote':
        result['remote'] = copy.deepcopy(spec['remote'])
        result['has_transfer'] = False
        result['capabilities'] = {'check': False, 'hints': False, 'transfer': False, 'remote': True}
        return result
    result['has_transfer'] = bool(spec.get('transfer'))
    result['capabilities'] = {'check': True, 'hints': True, 'transfer': result['has_transfer']}
    return result


def public_exercises(db=None):
    return [public_problem(spec) for spec in _all(db)]


def reference_problems():
    path = Path(os.environ.get('AI_REFERENCE_BANK') or ROOT / 'data/local-reference-bank.json')
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def languages_for(item):
    if item.get('engine') == 'luogu_remote':
        return ['python', 'cpp']
    return [item['language']] if item.get('language') else ['python']


def catalog_options(db=None):
    exercises = public_exercises(db)
    references = reference_problems()
    tags = sorted({tag for item in exercises + references for tag in item['tags']})
    sources = sorted({item['source']['name'] for item in exercises + references})
    has_cpp = any(item['engine'] == 'luogu_remote' for item in exercises) or \
        any(item['language'] == 'cpp' for item in references)
    return {'tags': tags, 'sources': sources, 'languages': ['python', 'cpp'] if has_cpp else ['python']}


def catalog(query='', tag='', difficulty='', source='', page=1, page_size=12, db=None, mode='all', category='', language=''):
    try:
        if type(page) is bool or type(page_size) is bool:
            raise ValueError()
        page, page_size = int(page), int(page_size)
        if page < 1 or not 1 <= page_size <= 100:
            raise ValueError()
    except (ValueError, TypeError, OverflowError) as exc:
        raise BankError('page must be positive and page_size must be between 1 and 100') from exc
    if mode not in ('all', 'local', 'remote', 'reference'):
        raise BankError('invalid catalog mode')
    if language not in ('', 'python', 'cpp'):
        raise BankError('invalid catalog language')
    tag = category or tag
    items = [item for item in public_exercises(db) if mode == 'all' or (item['engine'] == 'luogu_remote') == (mode == 'remote')]
    if mode == 'reference':
        items = []
    for item in items:
        item['languages'] = languages_for(item)
    if mode in ('all', 'reference'):
        items.extend(dict(item, languages=languages_for(item)) for item in reference_problems())
    query = query.casefold().strip()
    items = [item for item in items if
             (not query or query in ' '.join([item['id'], item['title'], item['description'], *item['tags']]).casefold())
             and (not tag or tag in item['tags'])
             and (not language or language in item['languages'])
             and (not difficulty or difficulty == item['difficulty'])
             and (not source or source == item['source']['name'])]
    return {'items': items[(page-1)*page_size:page*page_size], 'total': len(items), 'page': page, 'page_size': page_size}


def import_pack(path, db=None):
    pack = validate_pack(read_pack(path))
    ids = {item['id'] for item in _bundled()}
    if any(spec['id'] in ids for spec in pack['problems']):
        raise BankError('problem id collides with bundled problem')
    target = _db_path(db)
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
            raise BankError('problem id already imported') from exc
    return {'pack_id': pack['pack_id'], 'imported': len(pack['problems'])}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline question bank: validate, preview or import a JSON pack')
    parser.add_argument('--db')
    parser.add_argument('command', choices=('validate', 'preview', 'import'))
    parser.add_argument('path')
    args = parser.parse_args(argv)
    try:
        if args.command == 'import':
            result = import_pack(args.path, args.db)
        else:
            pack = validate_pack(read_pack(args.path))
            result = {'pack_id': pack['pack_id'], 'count': len(pack['problems'])}
            if args.command == 'preview':
                result['items'] = [public_problem(spec) for spec in pack['problems']]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BankError, OSError, sqlite3.Error, ValueError, TypeError, KeyError) as exc:
        parser.exit(1, f'question bank: {exc}\n')


if __name__ == '__main__':
    main()
