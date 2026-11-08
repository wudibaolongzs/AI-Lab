"""Private teacher material drafts; export never publishes into the question bank."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import hmac
import json
import sqlite3
import uuid
from urllib.parse import urlsplit
import classroom
import baidu_ocr
import question_bank


def _connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript('''CREATE TABLE IF NOT EXISTS material_drafts (
      id TEXT PRIMARY KEY, class_id TEXT NOT NULL, title TEXT NOT NULL,
      text TEXT NOT NULL, source_note TEXT NOT NULL, pack TEXT, ocr_log_id TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'pending_review', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
      updated_at TEXT DEFAULT CURRENT_TIMESTAMP);
      CREATE TABLE IF NOT EXISTS material_ocr_usage (
      class_id TEXT NOT NULL, day TEXT NOT NULL, calls INTEGER NOT NULL,
      PRIMARY KEY(class_id,day));''')
    if 'ocr_log_id' not in {row[1] for row in db.execute('PRAGMA table_info(material_drafts)')}:
        db.execute("ALTER TABLE material_drafts ADD COLUMN ocr_log_id TEXT NOT NULL DEFAULT ''")
        db.commit()
    return db


def _string(data, key, maximum):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(key)
    value.encode('utf-8')
    return value


def _draft(db, identifier, class_id):
    return db.execute('SELECT * FROM material_drafts WHERE id=? AND class_id=?', (identifier,class_id)).fetchone()


def _public(row):
    result = dict(row)
    result.pop('class_id',None)
    result['pack'] = json.loads(result['pack']) if result['pack'] else None
    return result


def dispatch(handler, payload=None):
    path = urlsplit(handler.path).path.rstrip('/')
    if path != '/api/materials' and not path.startswith('/api/materials/'):
        return False
    try:
        identities, classroom_db = classroom._config()
    except (OSError, ValueError, KeyError, TypeError):
        handler.reject(503,'课堂工作台未配置或配置无效'); return True
    token = handler.headers.get('X-Classroom-Token','')
    try:
        digest = hashlib.sha256(token.encode('utf-8')).digest()
    except (UnicodeError, AttributeError):
        handler.reject(401,'凭证无效'); return True
    identity = None
    for expected, class_id, role, _ in identities:
        if hmac.compare_digest(digest,expected): identity = (class_id,role)
    if identity is None:
        handler.reject(401,'凭证无效'); return True
    class_id, role = identity
    if role != 'teacher':
        handler.reject(403,'当前角色无权访问'); return True
    action = path[len('/api/materials'):].strip('/')
    if handler.command not in ('GET','POST') or (handler.command == 'POST' and action not in ('text','ocr','save','validate','export')):
        handler.reject(404,'接口不存在'); return True
    try:
        if handler.command == 'POST' and not isinstance(payload,dict): raise ValueError('body')
        with closing(_connect(classroom_db)) as db:
            if handler.command == 'GET':
                if not action:
                    rows = db.execute('SELECT id,title,status,created_at,updated_at FROM material_drafts WHERE class_id=? ORDER BY updated_at DESC,id DESC LIMIT 100',(class_id,))
                    handler.send_json(200,{'drafts':[dict(row) for row in rows],'ocr_enabled':baidu_ocr.enabled()})
                else:
                    row = _draft(db,action,class_id)
                    if row is None: handler.reject(404,'草稿不存在')
                    else: handler.send_json(200,_public(row))
                return True
            if action in ('text','ocr','save'):
                title = _string(payload,'title',160)
                note = _string(payload,'source_note',1000)
                if action != 'save' and payload.get('rights_confirmed') is not True: raise ValueError('rights')
                ocr_log_id = ''
                if action == 'ocr':
                    if payload.get('upload_confirmed') is not True: raise ValueError('upload')
                    image = _string(payload,'image',4*1024*1024)
                    if not baidu_ocr.enabled():
                        handler.reject(503,'OCR 未配置'); return True
                    day = datetime.now(timezone.utc).date().isoformat()
                    # Commit the reservation before network I/O; failures consume quota too.
                    with db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('INSERT OR IGNORE INTO material_ocr_usage VALUES(?,?,0)',(class_id,day))
                        cursor = db.execute('UPDATE material_ocr_usage SET calls=calls+1 WHERE class_id=? AND day=? AND calls<20',(class_id,day))
                    if not cursor.rowcount:
                        handler.reject(429,'今日班级 OCR 次数已用完'); return True
                    recognized = baidu_ocr.recognize(image)
                    text = _string(recognized,'text',20000)
                    ocr_log_id = str(recognized.get('log_id',''))[:80]
                else: text = _string(payload,'text',20000)
                pack = None
                if action == 'save':
                    identifier = _string(payload,'id',100)
                    if _draft(db,identifier,class_id) is None:
                        handler.reject(404,'草稿不存在'); return True
                    pack = payload.get('pack')
                    if pack is not None and not isinstance(pack,dict): raise ValueError('pack')
                    if pack is not None:
                        pack = json.dumps(pack,ensure_ascii=False,allow_nan=False)
                        if len(pack.encode('utf-8')) > 2*1024*1024: raise ValueError('pack')
                    with db:
                        db.execute("UPDATE material_drafts SET title=?,text=?,source_note=?,pack=?,status='pending_review',updated_at=CURRENT_TIMESTAMP WHERE id=? AND class_id=?",(title,text,note,pack,identifier,class_id))
                else:
                    identifier = uuid.uuid4().hex
                    with db:
                        db.execute('INSERT INTO material_drafts(id,class_id,title,text,source_note,ocr_log_id) VALUES(?,?,?,?,?,?)',(identifier,class_id,title,text,note,ocr_log_id))
                handler.send_json(200,_public(_draft(db,identifier,class_id)))
            else:
                identifier = _string(payload,'id',100)
                if action == 'export' and payload.get('review_confirmed') is not True: raise ValueError('review')
                row = _draft(db,identifier,class_id)
                if row is None:
                    handler.reject(404,'草稿不存在'); return True
                if not row['pack']: raise ValueError('pack')
                pack = json.loads(row['pack'])
                question_bank.validate_pack(pack,execute=True)
                handler.send_json(200,{'pack':pack} if action == 'export' else {'valid':True,'id':identifier,'status':'pending_review'})
    except baidu_ocr.OCRError as exc:
        handler.reject(exc.status, str(exc)[:300])
    except question_bank.BankError:
        handler.reject(400,'题包校验失败，请检查题目、来源授权、参考答案和测试用例')
    except (ValueError, TypeError, UnicodeError, RecursionError):
        handler.reject(400,'字段无效、缺少确认或超过长度限制')
    except sqlite3.Error:
        handler.reject(503,'草稿存储暂不可用')
    return True
