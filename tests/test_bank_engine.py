import unittest
import bank_engine


def spec(kind='number', expected=2):
    return {'signature': 'def solve(x):', 'parameters': [{'name': 'x', 'type': 'number'}],
            'return_type': kind, 'hints': ['Inspect input', 'Inspect branch', 'Try again'],
            'cases': [{'id': 'first', 'args': [1], 'expected': expected}]}


class BankEngineTests(unittest.TestCase):
    def test_arithmetic_and_branch(self):
        self.assertEqual(bank_engine.check('def solve(x):\n    if x > 0:\n        return x + 1\n    else:\n        return 0', spec())['status'], 'passed')

    def test_short_circuit(self):
        self.assertEqual(bank_engine.check('def solve(x):\n    return True or 1 / 0', spec('boolean', True))['status'], 'passed')

    def test_boolean_is_not_number(self):
        self.assertEqual(bank_engine.check('def solve(x):\n    return False', spec('number', 0))['status'], 'failed')

    def test_all_branches_validated(self):
        for expression in ('missing', 'x.__class__', 'solve(x)', '2 ** 4'):
            code = 'def solve(x):\n    if False:\n        return ' + expression + '\n    return 2'
            self.assertEqual(bank_engine.check(code, spec())['status'], 'invalid')

    def test_bounds_and_missing_return(self):
        self.assertEqual(bank_engine.check('def solve(x):\n    return ' + '9' * 3000, spec())['status'], 'invalid')
        for code in ('def solve(x):\n    return "a" * 1000000000000',
                     'def solve(x):\n    return 1 / 0',
                     'def solve(x):\n    x = 2'):
            result = bank_engine.check(code, spec())
            self.assertEqual(result['cases'][0]['status'], 'error')

    def test_reverse_and_membership(self):
        self.assertEqual(bank_engine.check('def solve(x):\n    return "abc"[::-1]', spec('string', 'cba'))['status'], 'passed')
        self.assertEqual(bank_engine.check('def solve(x):\n    return x in (1, 2)', spec('boolean', True))['status'], 'passed')

    def test_import_loop_builtin_assignment_rejected(self):
        for code in ('import os', 'def solve(x):\n    while True:\n        return 2', 'def solve(x):\n    sum = 2\n    return sum'):
            self.assertEqual(bank_engine.check(code, spec())['status'], 'invalid')


if __name__ == '__main__':
    unittest.main()
