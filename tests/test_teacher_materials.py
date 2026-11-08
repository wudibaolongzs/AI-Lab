import hashlib
import json
from pathlib import Path
import baidu_ocr
import question_bank
import tempfile
import unittest
from unittest.mock import patch
import teacher_materials as materials

class Handler:
    def __init__(self, method, route='', token='teacher'):
        self.command, self.path = method, '/api/materials' + ('/' + route if route else '')
        self.headers = {'X-Classroom-Token': token}
    def send_json(self, status, data): self.status, self.data = status, data
    def reject(self, status, message): self.send_json(status, {'error': message})

class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        identities = [(hashlib.sha256(t.encode()).digest(), c, r, '') for t,c,r in [('teacher','a','teacher'),('other','b','teacher'),('student','a','student')]]
        self.config = patch('classroom._config', return_value=(identities, self.tmp.name + '/db.sqlite'))
        self.config.start(); self.addCleanup(self.config.stop)
    def call(self, method, route='', payload=None, token='teacher'):
        h = Handler(method,route,token)
        self.assertTrue(materials.dispatch(h,payload))
        return h.status,h.data
    def create(self, **kw):
        return self.call('POST','text',dict(title='Title',text='Text',source_note='Own material',rights_confirmed=True,**kw))
    def test_auth_and_isolation(self):
        with patch('baidu_ocr.recognize') as cloud:
            self.assertEqual(self.call('POST','ocr',{},token='student')[0],403)
            self.assertEqual(self.call('POST','ocr',{},token='bad')[0],401)
            cloud.assert_not_called()
        status,draft=self.create(); self.assertEqual(status,200)
        self.assertEqual(self.call('GET',draft['id'],token='other')[0],404)
        self.assertEqual(self.call('GET',token='other')[1]['drafts'],[])
        self.assertNotIn('text', self.call('GET')[1]['drafts'][0])
    def test_ack_limits_and_save(self):
        for field,value in [('rights_confirmed',False),('title','x'*161),('text','x'*20001),('source_note','')]:
            data=dict(title='T',text='T',source_note='S',rights_confirmed=True);data[field]=value
            self.assertEqual(self.call('POST','text',data)[0],400)
        _,draft=self.create()
        self.assertEqual(self.call('POST','save',dict(id=draft['id'],title='T',text='T',source_note='S',pack={'a':'x'*2097152}))[0],400)
        self.assertEqual(self.call('POST','save',dict(id=draft['id'],title='T',text='T',source_note='S',pack=None))[0],200)
        self.assertEqual(self.call('POST','validate',{'id':draft['id']})[0],400)
    def test_validate_export(self):
        _,draft=self.create()
        data=dict(id=draft['id'],title='T',text='T',source_note='S',pack={'problems':[]})
        self.call('POST','save',data)
        with patch('question_bank.validate_pack', return_value=data['pack']) as validate:
            self.assertEqual(self.call('POST','validate',{'id':draft['id']})[0],200)
            self.assertEqual(self.call('POST','export',{'id':draft['id']})[0],400)
            self.assertEqual(self.call('POST','export',{'id':draft['id'],'review_confirmed':True})[1]['pack'],data['pack'])
            self.assertEqual(validate.call_count,2)
            self.assertTrue(validate.call_args.kwargs['execute'])
        self.assertEqual(self.call('GET',draft['id'])[1]['status'],'pending_review')
    def test_ocr_quota_and_disabled(self):
        data=dict(title='T',image='base64',source_note='S',upload_confirmed=True,rights_confirmed=True)
        with patch('baidu_ocr.enabled',return_value=False), patch('baidu_ocr.recognize') as cloud:
            self.assertEqual(self.call('POST','ocr',data)[0],503);cloud.assert_not_called()
        with patch('baidu_ocr.enabled',return_value=True), patch('baidu_ocr.recognize',return_value={'text':'recognized','log_id':'123'}) as cloud:
            self.assertEqual(self.call('POST','ocr',{**data,'upload_confirmed':False})[0],400)
            for _ in range(20): self.assertEqual(self.call('POST','ocr',data)[0],200)
            self.assertEqual(self.call('POST','ocr',data)[0],429)
            self.assertEqual(cloud.call_count,20)
        _,listing=self.call('GET')
        _,draft=self.call('GET',listing['drafts'][0]['id'])
        self.assertEqual(draft['text'],'recognized');self.assertNotIn('image',draft)
        self.assertEqual(draft['ocr_log_id'],'123')

    def test_real_valid_export_and_wrong_reference(self):
        _,draft=self.create()
        pack=json.loads(Path('data/example-import.json').read_text(encoding='utf-8'))
        data=dict(id=draft['id'],title='T',text='T',source_note='S',pack=pack)
        self.assertEqual(self.call('POST','save',data)[0],200)
        self.assertEqual(self.call('POST','validate',{'id':draft['id']})[0],200)
        status,exported=self.call('POST','export',{'id':draft['id'],'review_confirmed':True})
        self.assertEqual(status,200)
        self.assertEqual(exported['pack'],pack)
        pack['problems'][0]['reference_code']='def add_one(value):\n    return 999'
        self.assertEqual(self.call('POST','save',data)[0],200)
        self.assertEqual(self.call('POST','validate',{'id':draft['id']})[0],400)
        self.assertEqual(self.call('POST','export',{'id':draft['id'],'review_confirmed':True})[0],400)

    def test_real_source_validation_and_safe_errors(self):
        _,draft=self.create()
        pack=json.loads(Path('data/builtin.json').read_text(encoding='utf-8'))
        pack['problems']=pack['problems'][:1]
        pack['problems'][0]['source']['attribution']=''
        self.call('POST','save',dict(id=draft['id'],title='T',text='T',source_note='S',pack=pack))
        self.assertEqual(self.call('POST','validate',{'id':draft['id']})[0],400)
        self.assertEqual(self.call('POST','export',{'id':draft['id'],'review_confirmed':True})[0],400)
        with patch('question_bank.validate_pack',side_effect=question_bank.BankError('private code'*1000)):
            status,data=self.call('POST','validate',{'id':draft['id']})
            self.assertEqual(status,400)
            self.assertNotIn('private',data['error'])
            self.assertLess(len(data['error']),300)

    def test_ocr_failures_consume_quota_and_are_not_retried(self):
        data=dict(title='T',image='base64',source_note='S',upload_confirmed=True,rights_confirmed=True)
        with patch('baidu_ocr.enabled',return_value=True), patch('baidu_ocr.recognize',side_effect=baidu_ocr.OCRError(502,'OCR unavailable')) as cloud:
            for _ in range(20): self.assertEqual(self.call('POST','ocr',data)[0],502)
            self.assertEqual(self.call('POST','ocr',data)[0],429)
            self.assertEqual(cloud.call_count,20)
        self.assertEqual(self.call('GET')[1]['drafts'],[])

if __name__ == '__main__': unittest.main()


