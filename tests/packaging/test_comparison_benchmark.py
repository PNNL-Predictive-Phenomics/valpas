"""Bounded benchmark control flow; tiny inputs, no training or downloads."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class BenchmarkTests(unittest.TestCase):
    def run_benchmark(self, record, *extra):
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        return subprocess.run([sys.executable, str(ROOT / 'tools/benchmark_comparison.py'),
                               '--queries', '2', '--candidates', '3', '--outputs', '2',
                               '--record', str(record), *extra], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_small_completion_and_exclusive_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'record.json'
            process = self.run_benchmark(path)
            self.assertEqual(process.returncode, 0, process.stderr + process.stdout)
            record = json.loads(path.read_text())
            self.assertEqual(record['status'], 'passed')
            self.assertEqual(record['last_progress']['stage'], 'completed')
            self.assertEqual(record['pair_count'], 12)
            self.assertGreater(record['sampled_peak_rss_bytes'], 0)
            before = path.read_bytes()
            self.assertNotEqual(self.run_benchmark(path).returncode, 0)
            self.assertEqual(path.read_bytes(), before)

    def test_time_budget_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'record.json'
            process = self.run_benchmark(path, '--timeout', '.000001')
            self.assertEqual(process.returncode, 2, process.stderr)
            record = json.loads(path.read_text())
            self.assertEqual(record['status'], 'bounded_stop')
            self.assertEqual(record['stop_reason'], 'time_limit')


if __name__ == '__main__':
    unittest.main()
