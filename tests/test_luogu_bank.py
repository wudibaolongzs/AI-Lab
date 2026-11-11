import copy
import collections
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import question_bank as bank
from tools import luogu_bank


class LuoguBankTests(unittest.TestCase):
    def test_frozen_metadata(self):
        packs = [bank.read_pack(p) for p in sorted((bank.ROOT / 'data/luogu').glob('pack-*.json'))]
        self.assertEqual([len(luogu_bank.validate_pack(p)['problems']) for p in packs], [100, 100, 100])
        specs = [s for p in packs for s in p['problems']]
        manifest = bank.read_pack(bank.ROOT / 'data/luogu/selection-manifest.json')
        self.assertEqual(len({s['id'] for s in specs}), 300)
        self.assertEqual(dict(collections.Counter(s['tags'][0] for s in specs)), manifest['quotas'])
        for s in specs:
            self.assertEqual(s['source']['revision'], manifest['sha256_compressed'])
            self.assertFalse(s['remote']['statement_available'])
            self.assertFalse(luogu_bank.CONTENT_FIELDS.intersection(s))
            self.assertFalse(any(any(t in tag for t in ['交互', '提交答案', '远程', 'RemoteJudge']) for tag in s['remote']['official_tags']))
            self.assertIn(s['remote']['difficulty_original'], [1, 2])
            self.assertEqual(bank.public_problem(s)['capabilities'], {'check': False, 'hints': False, 'transfer': False, 'remote': True})

    def test_registry_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'bank.db'
            self.assertEqual(bank.catalog(db=db)['total'], 628)
            self.assertEqual(bank.catalog(db=db, mode='local')['total'], 28)
            self.assertEqual(bank.catalog(db=db, mode='remote')['total'], 300)
            self.assertEqual(bank.get_problem(bank.catalog(db=db, mode='remote')['items'][0]['id'], db)['engine'], 'luogu_remote')
            with self.assertRaises(bank.BankError): bank.catalog(db=db, mode='invalid')

    def test_separate_validation_and_authorization(self):
        pack = bank.read_pack(bank.ROOT / 'data/luogu/pack-1.json')
        with self.assertRaises(bank.BankError): bank.validate_pack(pack)
        altered = copy.deepcopy(pack)
        altered['problems'][0]['statement'] = 'content'
        with patch.dict('os.environ', {'LUOGU_CONTENT_AUTHORIZED': '0'}):
            with self.assertRaises(bank.BankError): luogu_bank.validate_pack(altered)
        altered = copy.deepcopy(pack)
        altered['problems'][1] = altered['problems'][0]
        with self.assertRaises(bank.BankError): luogu_bank.validate_pack(altered)

    def test_import_transaction(self):
        pack = bank.read_pack(bank.ROOT / 'data/luogu/pack-1.json')
        # New official-shaped IDs allow testing an external extension without overriding bundled IDs.
        pack['problems'] = copy.deepcopy(pack['problems'][:2])
        for i, s in enumerate(pack['problems']):
            pid = 'P' + str(900000 + i)
            s['id'] = 'luogu_' + pid
            s['remote']['pid'] = pid
            s['source']['url'] = 'https://www.luogu.com.cn/problem/' + pid
        with tempfile.TemporaryDirectory() as tmp:
            import json
            path, db = Path(tmp) / 'pack.json', Path(tmp) / 'bank.db'
            path.write_text(json.dumps(pack), encoding='utf8')
            self.assertEqual(luogu_bank.import_pack(path, db)['imported'], 2)
            with self.assertRaises(bank.BankError): luogu_bank.import_pack(path, db)
            self.assertEqual(bank.catalog(db=db)['total'], 630)
