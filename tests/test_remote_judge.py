from contextlib import closing
import hashlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
import remote_judge as remote

class Handler:
    def __init__(self, method, path, token='s'*24):
        self.command, self.path, self.headers = method, path, {'X-Classroom-Token': token}
    def send_json(self, status, data):
        self.status, self.data = status, data
    def reject(self, status, message):
        self.status, self.data = status, {'error': message}

class RemoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'LUOGU_DB': str(Path(self.tmp.name)/'remote.db'), 'LUOGU_ENABLED':'1', 'LUOGU_PROTOCOL_VERIFIED':'1', 'LUOGU_OPENAPP_TOKEN':'test:test'})
        self.env.start()
        identities = [(hashlib.sha256(t.encode()).digest(), c, r, s) for t,c,r,s in [('s'*24,'a','student','s'),('x'*24,'a','student','x'),('b'*24,'b','student','s'),('t'*24,'a','teacher','')]]
        self.auth = patch('classroom._config', return_value=(identities,'unused')); self.auth.start()
        self.bank = patch('question_bank.get_problem', return_value={'engine':'luogu_remote','remote':{'pid':'P1001'}}); self.bank.start()
        self.client = patch.object(remote, 'CLIENT'); self.mock = self.client.start()
        self.mock.submit.return_value={'requestId':'vendor-id'}
    def tearDown(self):
        self.client.stop(); self.bank.stop(); self.auth.stop(); self.env.stop(); self.tmp.cleanup()
    def post(self, nonce='one', **kwargs):
        payload=dict(exercise_id='luogu-P1001',language='python',code='print(1)',client_submission_id=nonce,upload_confirmed=True)
        payload.update(kwargs)
        h=Handler('POST','/api/remote/submissions'); remote.dispatch(h,payload); return h
    def test_transport_and_config(self):
        from luogu_client import Client, NoRedirect
        with patch.object(Client, '_request', return_value={}) as request:
            Client().submit('P1001', 'python3/c', 'code', 'track')
            self.assertEqual(request.call_args.args[1]['lang'], 'python3/c')
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://example.org'))
        self.assertEqual(remote.LANGUAGES['cpp'], 'cxx/17/gcc')
        h=Handler('GET','/api/remote/config');remote.dispatch(h)
        self.assertEqual(h.data['reason'],h.data['disabled_reason'])
        self.assertTrue(remote.enabled())
        with patch.dict(os.environ, {'LUOGU_ENABLED':'0'}):
            self.assertFalse(remote.enabled())
        for raw in [None, [], {'data':[]}, {'data':{'judge':[]}}, {'data':{'judge':'invalid'}}]:
            self.assertEqual(remote.normalize(raw)[0], 'judging')
        with patch.dict(os.environ, {'LUOGU_DB':''}), patch.object(remote.sqlite3,'connect',side_effect=RuntimeError('intercept')) as mock:
            with self.assertRaises(RuntimeError): remote.connect()
            self.assertEqual(mock.call_args.args[0], Path(remote.__file__).resolve().parent/'data/remote.sqlite3')
    def test_http_error_kinds(self):
        for status, kind in [(401,'auth'), (402,'quota'), (429,'limited')]:
            self.mock.submit.side_effect=HTTPError('https://redacted',status,'secret vendor message',None,None)
            result=self.post(str(status)).data
            self.assertEqual(result['status'],'error')
            self.assertEqual(result['result']['error_kind'],kind)
            self.assertEqual(result['result']['http_status'],status)
            self.assertNotIn('secret', json.dumps(result))
        self.mock.submit.side_effect=None
        record=self.post('poll-error').data['id']
        with closing(remote.connect()) as db:
            db.execute('UPDATE submissions SET next_poll=0 WHERE id=?',(record,));db.commit()
        self.mock.result.side_effect=HTTPError('https://redacted',402,'secret',None,None)
        h=Handler('GET','/api/remote/submissions/'+record);remote.dispatch(h)
        self.assertEqual(h.data['result']['error_kind'],'quota')
    def test_nonfinite_transport_json(self):
        from luogu_client import Client
        from unittest.mock import MagicMock
        for raw in [b'{"x":NaN}', b'{"x":Infinity}']:
            response=MagicMock();response.status=200;response.read.return_value=raw
            response.__enter__.return_value=response
            with patch('luogu_client.build_opener') as opener:
                opener.return_value.open.return_value=response
                with self.assertRaises(ValueError): Client().result('id')
    def test_foreign_result_never_cached(self):
        item=self.post().data
        for raw in [{'requestId':'foreign','data':{'judge':{'status':12}}}, {'trackId':'foreign','data':{'judge':{'status':12}}}]:
            with closing(remote.connect()) as db:
                db.execute('UPDATE submissions SET next_poll=0');db.commit()
            self.mock.result.return_value=raw
            h=Handler('GET','/api/remote/submissions/'+item['id']);remote.dispatch(h)
            self.assertIsNone(h.data['result'])
            self.assertEqual(h.data['status'],'judging')
    def test_busy_slots_no_submit(self):
        remote.SLOTS.acquire();remote.SLOTS.acquire()
        try:
            self.assertEqual(self.post().status,429)
            self.mock.submit.assert_not_called()
        finally:
            remote.SLOTS.release();remote.SLOTS.release()
    def test_global_daily_budget_persistent(self):
        self.post()
        with closing(remote.connect()) as db:
            row=list(db.execute('SELECT * FROM submissions').fetchone())
            for i in range(49):
                new=list(row);new[0]='seed'+str(i);new[1]='other';new[2]='student'+str(i);new[3]='nonce'+str(i)
                db.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',new)
            db.commit()
        self.assertEqual(self.post('second').status,429)
        self.mock.submit.assert_called_once()
    def test_code_limit(self):
        self.assertEqual(self.post(code='x'*4001).status,400)
        self.mock.submit.assert_not_called()
    def test_disabled(self):
        with patch.dict(os.environ,{'LUOGU_PROTOCOL_VERIFIED':'0'}):
            self.assertEqual(self.post().status,503)
        self.mock.submit.assert_not_called()
    def test_idempotency_and_private_source(self):
        first=self.post(); second=self.post()
        self.assertEqual(first.data['id'],second.data['id'])
        self.assertEqual(self.post(code='print(2)').status,409)
        self.mock.submit.assert_called_once()
        with closing(remote.connect()) as db:
            row=dict(db.execute('SELECT * FROM submissions').fetchone())
        self.assertNotIn('print(1)',json.dumps(row))
    def test_isolation(self):
        record=self.post().data['id']
        for token,expected in [('x'*24,404),('b'*24,404),('t'*24,403),('bad',401)]:
            h=Handler('GET','/api/remote/submissions/'+record,token);remote.dispatch(h);self.assertEqual(h.status,expected)
    def test_timeout_not_repeated_and_restart(self):
        self.mock.submit.side_effect=TimeoutError()
        self.assertEqual(self.post().data['status'],'uncertain');self.post()
        self.mock.submit.assert_called_once()
        with closing(remote.connect()) as db:
            db.execute("UPDATE submissions SET status='submitting',created=?",(remote.STARTED-1,));db.commit()
        with closing(remote.connect()) as db:
            self.assertEqual(db.execute('SELECT status FROM submissions').fetchone()[0],'uncertain')
    def test_budget(self):
        for i in range(10): self.assertEqual(self.post(str(i)).status,200)
        self.assertEqual(self.post('over').status,429)
        self.assertEqual(self.mock.submit.call_count,10)
    def test_statuses(self):
        for status in [0,1,999]:
            self.assertEqual(remote.normalize({'data':{'judge':{'status':status}}})[0],'judging')
        for status in remote.TERMINAL:
            self.assertEqual(remote.normalize({'data':{'judge':{'status':status,'score':60}}})[0],'completed')
        self.assertEqual(remote.normalize({'data':{'compile':{'success':True},'judge':None}})[0],'judging')
        self.assertEqual(remote.normalize({'data':{'compile':{'success':False}}})[0],'completed')
    def test_poll_throttle(self):
        item=self.post().data
        with closing(remote.connect()) as db:
            db.execute('UPDATE submissions SET next_poll=0');db.commit()
        self.mock.result.return_value={'data':{'judge':{'status':999}}}
        for _ in range(2):
            h=Handler('GET','/api/remote/submissions/'+item['id']);remote.dispatch(h)
        self.assertEqual(self.mock.result.call_count,1)
        self.assertEqual(h.data['result']['data']['judge']['status'],999)

if __name__=='__main__': unittest.main()
