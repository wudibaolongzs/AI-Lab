"""Opt-in local classroom queue; identity comes exclusively from bearer credentials."""
from contextlib import closing
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import uuid
from urllib.parse import urlsplit
from exercise import EXERCISES


def _config():
    path = os.environ.get('AI_CLASSROOM_CONFIG', '')
    db = os.environ.get('AI_CLASSROOM_DB', '')
    if not path or not db:
        raise ValueError('disabled')
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    classes = config['classes']
    if not isinstance(classes, dict) or not classes:
        raise ValueError('classes')
    identities, seen = [], set()
    for class_id, item in classes.items():
        if not isinstance(class_id, str) or not class_id or not isinstance(item['students'], dict):
            raise ValueError('class')
        entries = [('teacher', '', item['teacher_token'])]
        entries += [('student', student, token) for student, token in item['students'].items()]
        for role, student, token in entries:
            if not isinstance(student, str) or (role == 'student' and not student):
                raise ValueError('student')
            if not isinstance(token, str) or len(token) < 24 or not token.isascii() or any(c.isspace() for c in token) or token in seen:
                raise ValueError('credential')
            seen.add(token)
            identities.append((hashlib.sha256(token.encode()).digest(), class_id, role, student))
    return identities, db


def _connect(path):
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.executescript('''
      CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, class_id TEXT NOT NULL,
        exercise_id TEXT NOT NULL, title TEXT NOT NULL, due TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
      CREATE TABLE IF NOT EXISTS help(id TEXT PRIMARY KEY, class_id TEXT NOT NULL,
        student_id TEXT NOT NULL, exercise_id TEXT NOT NULL, submission_id TEXT NOT NULL,
        request_id TEXT NOT NULL, question TEXT NOT NULL, hint TEXT NOT NULL, source TEXT NOT NULL,
        reply TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(class_id,student_id,request_id));
    ''')
    return connection


def _string(payload, key, maximum, optional=False):
    value = payload.get(key, '' if optional else None)
    if not isinstance(value, str) or len(value) > maximum or (not optional and not value.strip()):
        raise ValueError(key)
    return value


def dispatch(handler, payload=None):
    path = urlsplit(handler.path).path
    if not path.startswith('/api/classroom/'):
        return False
    try:
        identities, db = _config()
    except (OSError, ValueError, KeyError, TypeError):
        handler.reject(503, '课堂工作台未配置或配置无效')
        return True
    authorization = handler.headers.get('Authorization', '')
    token = handler.headers.get('X-Classroom-Token', '') or (authorization[7:] if authorization.startswith('Bearer ') else '')
    digest = hashlib.sha256(token.encode()).digest()
    identity = None
    for expected, class_id, role, student in identities:
        if hmac.compare_digest(expected, digest):
            identity = (class_id, role, student)
    if identity is None:
        handler.reject(401, '凭证无效')
        return True
    class_id, role, student = identity
    routes = {('GET', '/api/classroom/student'): 'student',
              ('POST', '/api/classroom/help'): 'student',
              ('GET', '/api/classroom/teacher'): 'teacher',
              ('POST', '/api/classroom/tasks'): 'teacher',
              ('POST', '/api/classroom/reply'): 'teacher'}
    required = routes.get((handler.command, path))
    if required is None:
        handler.reject(404, '接口不存在')
        return True
    if role != required:
        handler.reject(403, '当前角色无权访问')
        return True
    try:
        if handler.command == 'POST' and not isinstance(payload, dict):
            raise ValueError('body')
        with closing(_connect(db)) as connection, connection:
            if handler.command == 'GET':
                tasks = [dict(row) for row in connection.execute('SELECT id,exercise_id,title,due,created_at FROM tasks WHERE class_id=? ORDER BY created_at,id', (class_id,))]
                query = 'SELECT * FROM help WHERE class_id=?'
                parameters = [class_id]
                if role == 'student':
                    query += ' AND student_id=?'
                    parameters.append(student)
                queue = [dict(row) for row in connection.execute(query + ' ORDER BY created_at,id', parameters)]
                result = {'class_id': class_id, 'tasks': tasks, 'help': queue}
                if role == 'teacher':
                    result['counts'] = {'tasks': len(tasks), 'help_requests': len(queue), 'unanswered': sum(not row['reply'] for row in queue)}
                handler.send_json(200, result)
            elif path.endswith('/reply'):
                help_id = _string(payload, 'help_id', 100)
                reply = _string(payload, 'reply', 1000)
                cursor = connection.execute('UPDATE help SET reply=? WHERE id=? AND class_id=?', (reply, help_id, class_id))
                if not cursor.rowcount:
                    handler.reject(404, '求助不存在')
                else:
                    handler.send_json(200, {'id': help_id, 'reply': reply})
            else:
                exercise_id = _string(payload, 'exercise_id', 80)
                if exercise_id not in EXERCISES:
                    raise ValueError('exercise_id')
                record_id = uuid.uuid4().hex
                if path.endswith('/tasks'):
                    title = _string(payload, 'title', 160)
                    due = _string(payload, 'due', 80, True)
                    connection.execute('INSERT INTO tasks(id,class_id,exercise_id,title,due) VALUES(?,?,?,?,?)', (record_id, class_id, exercise_id, title, due))
                else:
                    submission_id = _string(payload, 'submission_id', 100)
                    request_id = _string(payload, 'request_id', 100)
                    question = _string(payload, 'question', 1000)
                    hint = _string(payload, 'hint', 240, True)
                    source = _string(payload, 'source', 80)
                    if source not in ('local', 'ai', 'agentarts', 'deepseek', 'tencent', 'fallback', 'manual'):
                        raise ValueError('source')
                    existing = connection.execute('SELECT id FROM help WHERE class_id=? AND student_id=? AND request_id=?', (class_id, student, request_id)).fetchone()
                    if existing:
                        record_id = existing['id']
                    else:
                        connection.execute('INSERT INTO help(id,class_id,student_id,exercise_id,submission_id,request_id,question,hint,source) VALUES(?,?,?,?,?,?,?,?,?)', (record_id, class_id, student, exercise_id, submission_id, request_id, question, hint, source))
                handler.send_json(200, {'id': record_id})
    except ValueError:
        handler.reject(400, '字段无效或超过长度限制')
    except sqlite3.Error:
        handler.reject(503, '课堂存储暂不可用')
    return True
