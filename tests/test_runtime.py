"""Focused failure/thermal tests that never start GPU inference."""
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from clipboard_solver import ExamSolver


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.solver = ExamSolver()
        self.solver.settings = dict(self.solver.settings, min_request_interval_seconds=0, thermal_wait_seconds=0)

    def test_hot_gpu_prevents_inference(self):
        with patch('clipboard_solver.subprocess.check_output', return_value='90\n'), \
             patch.object(self.solver.model, 'chat') as chat:
            result = self.solver.solve('Which tag creates a paragraph?', dict(A='<p>', B='<x>', C='<y>', D='<z>'))
        chat.assert_not_called()
        self.assertIn('90', result['error'])

    def test_reference_outside_retrieved_set_rejected(self):
        with patch('clipboard_solver.subprocess.check_output', return_value='50\n'), \
             patch.object(self.solver.model, 'chat', return_value={'answer':'A','source':0}):
            result = self.solver.solve('Which tag creates a paragraph?', dict(A='<p>', B='<x>', C='<y>', D='<z>'))
        self.assertIn('error', result)

    def test_single_answer_cannot_be_multi(self):
        with patch('clipboard_solver.subprocess.check_output', return_value='50\n'), \
             patch.object(self.solver.model, 'chat', return_value={'answer':'A, B','source':1}):
            result = self.solver.solve('Which tag creates a paragraph?', dict(A='<p>', B='<x>', C='<y>', D='<z>'))
        self.assertIn('error', result)

    def test_cached_answers_do_not_start_model_again(self):
        with patch('clipboard_solver.subprocess.check_output', return_value='50\n'), \
             patch.object(self.solver.model, 'chat', return_value={'answer':'A','source':1}) as chat:
            options = dict(A='<p>', B='<x>', C='<y>', D='<z>')
            self.solver.solve('Which tag creates a paragraph?', options)
            second = self.solver.solve('Which tag creates a paragraph?', options)
        self.assertEqual(chat.call_count, 1)
        self.assertTrue(second['cached'])

    def test_insufficient_ram_fails_before_starting_process(self):
        with patch('psutil.virtual_memory', return_value=SimpleNamespace(available=500*1024*1024)), \
             patch('src.local_model.subprocess.Popen') as launch:
            with self.assertRaisesRegex(RuntimeError, 'RAM'):
                self.solver.model.start()
        launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
