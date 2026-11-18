"""Manifest CLI/public API parity and dependency-free A2 end-to-end guards."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_a1_contracts import FIXTURE, descriptor
from test_import_isolation import SubprocessCase, IMPORT_GUARD, IMPORT_ASSERTIONS
from valpas import cli
from valpas.comparison import (ComparisonSettings, compare_results, load_manifest,
                               load_comparison_bundle, write_comparison)


class CliCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def invoke(self, extra=()):
        argv = ['valpas', 'compare', '--manifest', str(FIXTURE / 'manifest.json'),
                '--outdir', str(self.root / 'cli'), *extra]
        out, err = io.StringIO(), io.StringIO()
        with patch('sys.argv', argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            cli.main()
        return out.getvalue(), err.getvalue()

    def test_cli_overrides_and_api_parity(self):
        stdout, stderr = self.invoke(['--pool', 'common', '--depths', '1', '2', '--tables-only'])
        cli_result = load_comparison_bundle(self.root / 'cli')
        manifest = load_manifest(FIXTURE / 'manifest.json')
        settings = manifest.settings.to_dict()
        settings.update(pool_policy='common', depths=[1, 2])
        api = compare_results(manifest, ComparisonSettings.from_dict(settings))
        self.assertEqual(cli_result.comparison_id, api.comparison_id)
        for name in api.table_names:
            self.assertEqual(list(cli_result.iter_table(name)), list(api.iter_table(name)))
        self.assertIn(api.comparison_id, stdout)
        self.assertIn('no HTML', stdout)
        self.assertIn('2/2 queries', stdout)
        self.assertIn('Warning:', stderr)

    def test_cli_calls_public_loader_engine_and_writer(self):
        with patch('valpas.comparison.load_manifest', wraps=load_manifest) as loader, \
             patch('valpas.comparison.compare_results', wraps=compare_results) as engine, \
             patch('valpas.comparison.write_comparison', wraps=write_comparison) as writer:
            self.invoke()
        loader.assert_called_once_with(FIXTURE / 'manifest.json')
        engine.assert_called_once()
        writer.assert_called_once()
        self.assertFalse(writer.call_args.kwargs['tables_only'])
        self.assertFalse(writer.call_args.kwargs['overwrite'])
        self.assertEqual(writer.call_args.kwargs['report_settings'].max_interactive_depth, 50)

    def test_cli_failures_nonzero_actionable_without_tracebacks(self):
        empty = json.loads((FIXTURE / 'manifest.json').read_text())
        empty['outputs'] = [descriptor('a', [None, None, None]), descriptor('b')]
        empty_path = self.root / 'empty.json'
        empty_path.write_text(json.dumps(empty))
        malformed_path = self.root / 'malformed.json'
        malformed_path.write_text('{not JSON}')
        cases = [(['--depths', '0'], 'depths'), (['--manifest', str(self.root / 'missing.json')], 'local JSON manifest'),
                 (['--pool', 'guess'], 'invalid choice'),
                 (['--manifest', str(empty_path), '--pool', 'common'], 'empty common scorable pool'),
                 (['--manifest', str(malformed_path)], 'JSON')]
        for args, message in cases:
            with self.subTest(args=args):
                err = io.StringIO()
                with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
                    self.invoke_failure(args)
                self.assertEqual(caught.exception.code, 2)
                self.assertIn(message, err.getvalue())
                self.assertNotIn('Traceback', err.getvalue())
                self.assertFalse((self.root / 'cli').exists())

    def invoke_failure(self, args):
        with patch('sys.argv', ['valpas', 'compare', '--manifest', str(FIXTURE / 'manifest.json'),
                               '--outdir', str(self.root / 'cli'), *args]):
            cli.main()

    def test_cli_default_refusal_safe_overwrite_and_foreign_file_refusal(self):
        self.invoke()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke_failure([])
        self.invoke(['--overwrite'])
        (self.root / 'cli' / 'keep.txt').write_text('keep')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.invoke_failure(['--overwrite'])
        self.assertEqual((self.root / 'cli' / 'keep.txt').read_text(), 'keep')


class LightweightA2Case(SubprocessCase):
    def test_full_a2_api_and_cli_preserve_import_and_warning_state(self):
        self.run_python(IMPORT_GUARD + f'''
from pathlib import Path
from unittest.mock import patch
from valpas.comparison import load_manifest, compare_results, write_comparison, load_comparison_bundle
from valpas import cli
manifest = load_manifest({str(FIXTURE / 'manifest.json')!r})
result = compare_results(manifest)
path = write_comparison(result, 'api-bundle')
loaded = load_comparison_bundle(path)
assert loaded.comparison_id == result.comparison_id
for name in result.table_names:
    assert list(loaded.iter_table(name)) == list(result.iter_table(name))
with patch('sys.argv', ['valpas', 'compare', '--manifest', {str(FIXTURE / 'manifest.json')!r}, '--outdir', 'cli-bundle']):
    cli.main()
assert load_comparison_bundle('cli-bundle').comparison_id == result.comparison_id
with patch('sys.argv', ['valpas', 'compare', '--help']):
    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 0
    else:
        raise AssertionError('expected help exit')
''' + IMPORT_ASSERTIONS)


if __name__ == '__main__':
    unittest.main()
