"""Opt-in remote judge. Sources stay in memory; durable IDs prevent resubmission."""
from contextlib import closing
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
import sqlite3
import threading
import time
import uuid
from urllib.parse import urlsplit
from urllib.error import HTTPError
from luogu_client import Client

CLIENT = Client()
SLOTS = threading.BoundedSemaphore(2)
LANGUAGES = {'python': 'python3/c', 'python3/c': 'python3/c', 'cpp': 'cxx/17/gcc', 'cxx/17/gcc': 'cxx/17/gcc'}
TERMINAL = {2, 3, 4, 5, 6, 7, 11, 12, 14}
STARTED = time.time()

def enabled():
    return os.environ.get('LUOGU_ENABLED') == '1' and os.environ.get('LUOGU_PROTOCOL_VERIFIED') == '1' and bool(os.environ.get('LUOGU_OPENAPP_TOKEN'))

def connect():
    path = Path(os.environ.get('LUOGU_DB') or Path(__file__).resolve().parent / 'data/remote.sqlite3')
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('''CREATE TABLE IF NOT EXISTS submissions(
      id TEXT PRIMARY KEY, class_id TEXT, student_id TEXT, client_id TEXT,
      exercise_id TEXT, language TEXT, code_sha TEXT, track_id TEXT,
      request_id TEXT, status TEXT, result TEXT, created REAL, next_poll REAL,
      UNIQUE(class_id,student_id,client_id))''')
    # Only records predating this process are recovered. Concurrent requests must
    # never invalidate an active submit in this process.
    db.execute("UPDATE submissions SET status='uncertain' WHERE status='submitting' AND created<?", (STARTED,))
    db.commit()
    return db

def output(row):
    return {'id': row['id'], 'status': row['status'], 'request_id': row['request_id'],
            'track_id': row['track_id'], 'result': json.loads(row['result']) if row['result'] else None,
            'source': 'luogu', 'language': row['language'], 'exercise_id': row['exercise_id'],
            'next_poll_seconds': max(0, int(row['next_poll'] - time.time()) + 1)}


def transport_error(status):
    kinds = {401: ('auth', 'Remote authentication failed'), 403: ('auth', 'Remote access denied'),
             402: ('quota', 'Remote account quota unavailable'),
             429: ('limited', 'Remote rate limit reached'),
             400: ('invalid', 'Remote request rejected'), 404: ('invalid', 'Remote resource unavailable')}
    kind, message = kinds.get(status, ('unknown', 'Remote transport failed'))
    return json.dumps({'error_kind': kind, 'error_message': message, 'http_status': status})

def normalize(raw):
    if not isinstance(raw, dict):
        return 'judging', raw
    data = raw.get('data')
    if not isinstance(data, dict):
        return 'judging', raw
    judge = data.get('judge')
    if not isinstance(judge, dict):
        judge = {}
    status = judge.get('status')
    if type(status) is int and status in TERMINAL:
        return 'completed', raw
    if isinstance(data.get('compile'), dict) and data['compile'].get('success') is False:
        return 'completed', raw
    return 'judging', raw

def dispatch(handler, payload=None):
    path = urlsplit(handler.path).path
    if not path.startswith('/api/remote/'):
        return False
    if handler.command == 'GET' and path == '/api/remote/config':
        reason = '' if enabled() else 'Remote judge disabled; official result URL parameter placement requires vendor verification'
        handler.send_json(200, {'enabled': enabled(), 'protocol_verified': os.environ.get('LUOGU_PROTOCOL_VERIFIED') == '1', 'disabled_reason': reason, 'reason': reason})
        return True
    try:
        import classroom
        identities, _ = classroom._config()
    except (ValueError, OSError, KeyError, TypeError):
        handler.reject(503, '课堂身份未配置')
        return True
    digest = hashlib.sha256(handler.headers.get('X-Classroom-Token', '').encode()).digest()
    identity = next(((c, r, s) for expected, c, r, s in identities if hmac.compare_digest(expected, digest)), None)
    if identity is None:
        handler.reject(401, '凭证无效')
        return True
    class_id, role, student = identity
    if role != 'student':
        handler.reject(403, '仅学生可使用远程评测')
        return True
    try:
        with closing(connect()) as db:
            if handler.command == 'GET' and path.startswith('/api/remote/submissions/'):
                local_id = path.rsplit('/', 1)[1]
                if not re.fullmatch(r'[0-9a-f]{32}', local_id):
                    handler.reject(404, 'Record unavailable')
                    return True
                row = db.execute('SELECT * FROM submissions WHERE id=? AND class_id=? AND student_id=?', (local_id, class_id, student)).fetchone()
                if row is None:
                    handler.reject(404, '记录不存在')
                    return True
                now = time.time()
                if row['status'] == 'judging' and now >= row['next_poll']:
                    if now - row['created'] >= 3600:
                        db.execute("UPDATE submissions SET status='expired' WHERE id=?", (row['id'],))
                        db.commit()
                    elif enabled():
                        db.execute('BEGIN IMMEDIATE')
                        current = db.execute('SELECT * FROM submissions WHERE id=?', (row['id'],)).fetchone()
                        if current['next_poll'] <= now:
                            delay = 2 if now-row['created'] < 20 else 5 if now-row['created'] < 60 else 10
                            db.execute('UPDATE submissions SET next_poll=? WHERE id=?', (now+delay, row['id']))
                            db.commit()
                            if SLOTS.acquire(blocking=False):
                                try:
                                    raw = CLIENT.result(row['request_id'])
                                    if isinstance(raw, dict) and any(key in raw and raw[key] != row[column] for key, column in (('requestId', 'request_id'), ('trackId', 'track_id'))):
                                        raise ValueError('Mismatched remote result identity')
                                    status, result = normalize(raw)
                                    db.execute('UPDATE submissions SET status=?,result=? WHERE id=?', (status, json.dumps(result), row['id']))
                                    db.commit()
                                except HTTPError as exc:
                                    db.execute("UPDATE submissions SET status='error',result=? WHERE id=?", (transport_error(exc.code), row['id']))
                                    db.commit()
                                except Exception:
                                    pass  # Read timeout preserves the previous partial result.
                                finally:
                                    SLOTS.release()
                        else:
                            db.commit()
                row = db.execute('SELECT * FROM submissions WHERE id=?', (row['id'],)).fetchone()
                handler.send_json(200, output(row))
                return True
            if handler.command != 'POST' or path != '/api/remote/submissions':
                handler.reject(404, '接口不存在')
                return True
            if not isinstance(payload, dict) or payload.get('upload_confirmed') is not True:
                raise ValueError('confirmation')
            for key, limit in [('exercise_id', 100), ('client_submission_id', 100), ('language', 30), ('code', 4000)]:
                if not isinstance(payload.get(key), str) or not payload[key].strip() or len(payload[key]) > limit:
                    raise ValueError(key)
            existing = db.execute('SELECT * FROM submissions WHERE class_id=? AND student_id=? AND client_id=?', (class_id, student, payload['client_submission_id'])).fetchone()
            if existing:
                if (existing['code_sha'], existing['language'], existing['exercise_id']) != (hashlib.sha256(payload['code'].encode()).hexdigest(), payload['language'], payload['exercise_id']):
                    handler.reject(409, '客户端提交标识已用于其他内容')
                    return True
                handler.send_json(200, output(existing))
                return True
            if not enabled():
                handler.reject(503, '远程评测未启用或协议尚未核验')
                return True
            import question_bank
            spec = question_bank.get_problem(payload['exercise_id'])
            if spec.get('engine') != 'luogu_remote':
                raise ValueError('engine')
            pid = (spec.get('remote') or {}).get('pid') or spec.get('remote_pid') or spec.get('source', {}).get('pid')
            language = LANGUAGES.get(payload['language'])
            if not pid or not language:
                raise ValueError('remote')
            if not SLOTS.acquire(blocking=False):
                handler.reject(429, '远程评测繁忙')
                return True
            try:
                now = time.time()
                db.execute('BEGIN IMMEDIATE')
                existing = db.execute('SELECT * FROM submissions WHERE class_id=? AND student_id=? AND client_id=?', (class_id, student, payload['client_submission_id'])).fetchone()
                if existing:
                    db.commit()
                    if (existing['code_sha'], existing['language'], existing['exercise_id']) != (hashlib.sha256(payload['code'].encode()).hexdigest(), payload['language'], payload['exercise_id']):
                        handler.reject(409, '客户端提交标识已用于其他内容')
                        return True
                    handler.send_json(200, output(existing))
                    return True
                hourly = db.execute('SELECT count(*) FROM submissions WHERE class_id=? AND student_id=? AND created>?', (class_id, student, now-3600)).fetchone()[0]
                daily = db.execute('SELECT count(*) FROM submissions WHERE created>?', (now-86400,)).fetchone()[0]
                if hourly >= 10 or daily >= 50:
                    db.rollback()
                    handler.reject(429, '评测额度已达限制')
                    return True
                local_id, track = uuid.uuid4().hex, uuid.uuid4().hex
                db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)', (local_id, class_id, student, payload['client_submission_id'], payload['exercise_id'], payload['language'], hashlib.sha256(payload['code'].encode()).hexdigest(), track, None, 'submitting', None, now, now+2))
                db.commit()
                try:
                    response = CLIENT.submit(pid, language, payload['code'], track)
                    request_id = response.get('requestId') if isinstance(response, dict) else None
                    if not isinstance(request_id, str) or not request_id:
                        raise ValueError('Missing request ID')
                    db.execute("UPDATE submissions SET status='judging',request_id=? WHERE id=?", (request_id, local_id))
                except HTTPError as exc:
                    status = 'error' if exc.code in (400, 401, 402, 403, 404, 429) else 'uncertain'
                    db.execute('UPDATE submissions SET status=?,result=? WHERE id=?', (status, transport_error(exc.code), local_id))
                except Exception:
                    db.execute("UPDATE submissions SET status='uncertain' WHERE id=?", (local_id,))
                db.commit()
                handler.send_json(200, output(db.execute('SELECT * FROM submissions WHERE id=?', (local_id,)).fetchone()))
            finally:
                SLOTS.release()
    except (ValueError, KeyError, TypeError):
        handler.reject(400, '字段或题目无效')
    except (sqlite3.Error, OSError):
        handler.reject(503, '远程评测存储暂不可用')
    return True
