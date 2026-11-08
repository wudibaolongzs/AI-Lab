import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import question_bank as bank


def fixture():
    return {'schema_version': 1, 'pack_id': 'test', 'version': '1', 'problems': [{
        'id': 'local_test', 'version': '1', 'title': 'A', 'description': 'Add one.',
        'learning_goal': 'Addition', 'tags': ['arithmetic'], 'difficulty': 'easy',
        'source': {key: 'test' for key in ('name', 'url', 'revision', 'license', 'attribution', 'adaptation')},
        'signature': 'def plus(value):', 'parameters': [{'name': 'value', 'type': 'number'}],
        'return_type': 'number', 'starter_code': 'def plus(value):\n    return value',
        'reference_code': 'def plus(value):\n    return value + 1',
        'cases': [{'id': 'one', 'args': [2], 'expected': 3}],
        'hints': ['Input', 'Addition', 'One'], 'engine': 'bounded_v1'}]}


class BankTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'bank.sqlite3'
        self.pack = self.root / 'pack.json'
        self.patch = patch.object(bank, 'BUNDLED_PATHS', ())
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def write(self, value):
        self.pack.write_text(json.dumps(value), encoding='utf-8')

    def test_read_does_not_create_database_and_projection_is_private(self):
        self.assertEqual(bank.public_exercises(self.db), [])
        self.assertFalse(self.db.exists())
        self.write(fixture())
        bank.import_pack(self.pack, self.db)
        item = bank.public_exercises(self.db)[0]
        self.assertFalse({'reference_code', 'cases', 'hints', 'transfer'} & item.keys())
        self.assertEqual(item['source']['attribution'], 'test')
        self.assertEqual(bank.get_problem('local_test', self.db)['cases'][0]['expected'], 3)

    def test_rejects_invalid_before_creating_database(self):
        for change in ({'reference_code': 'def plus(value):\n    return 0'},
                       {'starter_code': 'def plus(value):\n    return value + 1'},
                       {'starter_code': 'import os'},
                       {'reference_code': 'import os'},
                       {'signature': '('},
                       {'title': '\ud800'},
                       {'engine': 'legacy'}, {'difficulty': True},
                       {'transfer': {'question_id': 'q', 'question': 'q', 'answer': True}}):
            pack = fixture()
            pack['problems'][0].update(change)
            self.write(pack)
            with self.assertRaises(bank.BankError):
                bank.import_pack(self.pack, self.db)
            self.assertFalse(self.db.exists())

    def test_page_boundaries_and_oversized_numbers(self):
        for page, size in ((0, 12), (1, 0), (1, 101), (True, 12), ('bad', 12)):
            with self.assertRaises(bank.BankError):
                bank.catalog(page=page, page_size=size, db=self.db)
        pack = fixture()
        pack['problems'][0]['cases'][0]['args'] = [10 ** 1000]
        with self.assertRaises(bank.BankError):
            bank.validate_pack(pack)

    def test_public_source_whitelist(self):
        spec = fixture()['problems'][0]
        spec['source']['reference_code'] = 'secret'
        self.assertNotIn('reference_code', bank.public_problem(spec)['source'])

    def test_collision_rolls_back_entire_pack_and_reads_refresh(self):
        self.write(fixture())
        bank.import_pack(self.pack, self.db)
        pack = fixture()
        other = copy.deepcopy(pack['problems'][0])
        other['id'] = 'fresh'
        pack['problems'].insert(0, other)
        self.write(pack)
        with self.assertRaises(bank.BankError):
            bank.import_pack(self.pack, self.db)
        self.assertEqual(len(bank.public_exercises(self.db)), 1)
        pack['problems'] = [other]
        self.write(pack)
        bank.import_pack(self.pack, self.db)
        self.assertEqual(len(bank.public_exercises(self.db)), 2)
        self.assertEqual(bank.catalog(tag='arithmetic', page=2, page_size=1, db=self.db)['items'][0]['id'], 'fresh')

    def test_duplicate_within_pack_and_bundled_collision(self):
        pack = fixture()
        pack['problems'] *= 2
        with self.assertRaises(bank.BankError):
            bank.validate_pack(pack)
        self.write(fixture())
        with patch.object(bank, '_bundled', return_value=fixture()['problems']):
            with self.assertRaises(bank.BankError):
                bank.import_pack(self.pack, self.db)
        self.assertFalse(self.db.exists())


if __name__ == '__main__':
    unittest.main()
