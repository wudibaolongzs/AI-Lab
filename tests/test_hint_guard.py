import threading
import unittest
from unittest.mock import patch

import hint_guard
from agentarts import get_hint
from exercise import EXERCISE, check_submission


class HintGuardTests(unittest.TestCase):
    def setUp(self):
        hint_guard.reset()
        self.addCleanup(hint_guard.reset)
        self.now = 0
        self.guard = hint_guard.HintGuard(lambda: self.now)

    def test_cache_key_separates_every_configuration_and_evidence_dimension(self):
        base = ['agentarts', 'model', 'https://example.test', 'credential', 'average', {'cases': [1]}, 1]
        original = hint_guard.cache_key(*base)
        for index, value in enumerate(['deepseek', 'other', 'https://other.test', 'rotated', 'sum', {'cases': [2]}, 2]):
            changed = list(base)
            changed[index] = value
            self.assertNotEqual(original, hint_guard.cache_key(*changed))

    def test_cache_expiry_capacity_and_key_privacy(self):
        key = hint_guard.cache_key('p', 'm', 'https://secret', 'credential', 'e', {'case': 1}, 1)
        self.assertNotIn('credential', key)
        for n in range(257):
            self.guard.finish(str(n), {'hint': 'safe'})
        self.assertEqual(len(self.guard.cache), 256)
        self.assertNotIn('0', self.guard.cache)
        self.assertEqual(self.guard.begin('256')[0], 'cached')
        self.now = 300
        self.assertEqual(self.guard.begin('256')[0], 'allowed')

    def test_sliding_global_budget_and_no_charge_for_duplicate(self):
        for n in range(6):
            self.assertEqual(self.guard.begin(str(n))[0], 'allowed')
            self.assertEqual(self.guard.begin(str(n))[0], 'busy')
            self.guard.finish(str(n), {'hint': 'safe'})
        self.assertEqual(self.guard.begin('new')[0], 'rate_limited')
        self.assertEqual(self.guard.begin('0')[0], 'cached')
        self.now = 60
        self.assertEqual(self.guard.begin('new')[0], 'allowed')

    def test_circuit_one_half_open_probe_then_recovery(self):
        for n in range(3):
            self.assertEqual(self.guard.begin(str(n))[0], 'allowed')
            self.guard.finish(str(n))
        self.assertEqual(self.guard.begin('x')[0], 'circuit_open')
        self.now = 30
        self.assertEqual(self.guard.begin('probe')[0], 'allowed')
        self.assertEqual(self.guard.begin('other')[0], 'circuit_open')
        self.guard.finish('probe')
        self.assertEqual(self.guard.begin('other')[0], 'circuit_open')
        self.now = 60
        self.assertEqual(self.guard.begin('probe')[0], 'allowed')
        self.guard.finish('probe', {'hint': 'safe'})
        self.assertEqual(self.guard.begin('other')[0], 'allowed')

    def test_threads_admit_only_two_and_duplicate_never_waits(self):
        gate = threading.Barrier(9)
        results = []
        def run(n):
            gate.wait()
            results.append(self.guard.begin(str(n))[0])
        threads = [threading.Thread(target=run, args=(n,)) for n in range(8)]
        for thread in threads:
            thread.start()
        gate.wait()
        for thread in threads:
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.assertEqual(results.count('allowed'), 2)
        self.assertEqual(results.count('busy'), 6)

    def test_success_cache_preserves_new_request_id_and_provider_dimensions(self):
        result = check_submission(EXERCISE['starter_code'])
        env = {'AI_HINT_PROTECTION': '1', 'AI_PROVIDER': 'agentarts',
               'AGENTARTS_EXERCISES': '', 'AGENTARTS_WORKFLOW_URL': 'https://example.test',
               'AGENTARTS_API_KEY': 'private'}
        with patch.dict('os.environ', env), patch('agentarts._invoke', return_value=(
                {'hint': '检查失败用例的元素数量。', 'case_id': 'C01'}, 'execution')) as invoke:
            first = get_hint('average', result, 1)
            with self.assertLogs('agentarts', level='INFO') as logs:
                second = get_hint('average', result, 1)
            self.assertTrue(second['cache_hit'])
            self.assertNotEqual(first['request_id'], second['request_id'])
            self.assertEqual(second['execution_id'], 'execution')
            self.assertIn(second['request_id'], logs.output[0])
            self.assertNotIn('private', logs.output[0])
            invoke.assert_called_once()
            with patch.dict('os.environ', {'AGENTARTS_API_KEY': 'rotated'}):
                get_hint('average', result, 1)
            self.assertEqual(invoke.call_count, 2)

    def test_failure_is_not_cached_and_invalid_scope_never_calls(self):
        result = check_submission(EXERCISE['starter_code'])
        env = {'AI_HINT_PROTECTION': '1', 'AI_PROVIDER': 'agentarts',
               'AGENTARTS_EXERCISES': '', 'AGENTARTS_WORKFLOW_URL': 'https://example.test',
               'AGENTARTS_API_KEY': 'private'}
        with patch.dict('os.environ', env), patch('agentarts._invoke', side_effect=TimeoutError) as invoke:
            for _ in range(3):
                self.assertEqual(get_hint('average', result, 1)['fallback_reason'], 'timeout')
            self.assertEqual(get_hint('average', result, 1)['fallback_reason'], 'circuit_open')
            self.assertEqual(invoke.call_count, 3)
