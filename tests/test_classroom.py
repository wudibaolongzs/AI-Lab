import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import classroom


class Handler:
    def __init__(self, method, route, token=''):
        self.command, self.path = method, '/api/classroom/' + route
        self.headers = {'Authorization': 'Bearer ' + token}
    def send_json(self, status, data):
        self.status, self.data = status, data
    def reject(self, status, message):
        self.send_json(status, {'error': message})


class ClassroomTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.teacher, self.student, self.other = 't'*32, 's'*32, 'o'*32
        config = {'classes': {'a': {'teacher_token': self.teacher, 'students': {'s1': self.student, 's2': 'v'*32}}, 'b': {'teacher_token': self.other, 'students': {}}}}
        (root/'config.json').write_text(json.dumps(config), encoding='utf-8')
        self.env = patch.dict(os.environ, {'AI_CLASSROOM_CONFIG': str(root/'config.json'), 'AI_CLASSROOM_DB': str(root/'classroom.sqlite')})
        self.env.start()
        self.addCleanup(self.env.stop)
    def call(self, method, route, token='', payload=None):
        handler = Handler(method, route, token)
        self.assertTrue(classroom.dispatch(handler, payload))
        return handler.status, handler.data
    def help(self, **changes):
        return dict(exercise_id='average', submission_id='run1', request_id='r1', question='How?', hint='Think', source='manual', **changes)
    def test_auth_disabled_and_roles(self):
        self.assertEqual(self.call('GET','teacher')[0],401)
        self.assertEqual(self.call('GET','teacher','wrong')[0],401)
        self.assertEqual(self.call('GET','teacher',self.student)[0],403)
        self.assertEqual(self.call('POST','help',self.teacher,{})[0],403)
        with patch.dict(os.environ, {'AI_CLASSROOM_CONFIG':''}):
            self.assertEqual(self.call('GET','teacher')[0],503)
    def test_persistence_and_class_ownership(self):
        status, data = self.call('POST','help',self.student,self.help())
        self.assertEqual(status,200)
        identifier = data['id']
        self.assertEqual(self.call('GET','teacher',self.other)[1]['help'],[])
        self.assertEqual(self.call('POST','reply',self.other,{'help_id':identifier,'reply':'foreign'})[0],404)
        self.assertEqual(self.call('POST','reply',self.teacher,{'help_id':identifier,'reply':'Try again'})[0],200)
        own = self.call('GET','student',self.student)[1]['help']
        self.assertEqual(own[0]['reply'],'Try again')
        self.assertEqual(self.call('GET','student','v'*32)[1]['help'],[])
        self.assertEqual(self.call('POST','help',self.student,self.help())[1]['id'],identifier)
        self.assertEqual(len(self.call('GET','teacher',self.teacher)[1]['help']),1)
    def test_custom_token_coexists_with_gateway_basic_auth(self):
        handler=Handler("GET","teacher")
        handler.headers={"Authorization":"Basic gateway", "X-Classroom-Token":self.teacher}
        classroom.dispatch(handler)
        self.assertEqual(handler.status,200)

    def test_invalid_unicode_is_client_error(self):
        self.assertEqual(self.call("POST","help",self.student,{**self.help(),"question":chr(0xd800)})[0],400)

    def test_validation_tasks_and_unknown(self):
        self.assertEqual(self.call('POST','help',self.student,{**self.help(),'question':'x'*1001})[0],400)
        self.assertEqual(self.call('POST','help',self.student,{**self.help(),'source':'raw source code'})[0],400)
        self.assertEqual(self.call('POST','tasks',self.teacher,{'exercise_id':'missing','title':'X'})[0],400)
        self.assertEqual(self.call('POST','tasks',self.teacher,{'exercise_id':'average','title':'Practice'})[0],200)
        self.assertEqual(len(self.call('GET','student',self.student)[1]['tasks']),1)
        self.assertEqual(self.call('GET','teacher',self.other)[1]['tasks'],[])
        self.assertEqual(self.call('GET','unknown',self.teacher)[0],404)


if __name__ == '__main__':
    unittest.main()
