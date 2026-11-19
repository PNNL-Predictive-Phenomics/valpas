"""Real vector export, source-free CLI, literal text, and no-clobber regressions."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from test_a1_contracts import descriptor, FIXTURE
from test_a3_report import fixture_result, profile_layer
from test_b1_persistence import b1_result, digest_record
from test_b2_session import chosen
from test_import_isolation import IMPORT_GUARD, IMPORT_ASSERTIONS, SubprocessCase
from valpas.comparison import (export_query_figure, compare_results, load_comparison_input,
    load_comparison_bundle, write_comparison, load_manifest, ProfileData, ReportSettings,
    ComparisonValidationError)
from valpas.comparison.browser import build_report_payload

HOSTILE = '$\\notacommand_{x}$ </script><script>globalThis.pwned=true</script> & < > " Ω'
SVG = '{http://www.w3.org/2000/svg}'


def hostile_result(same=False):
    outputs = []
    query, candidate = '001 ' + HOSTILE, ' ../../candidate ' + HOSTILE
    for oid in ('a', 'b'):
        d = descriptor(oid)
        if same:
            d['identity']['candidate_namespace'] = d['identity']['query_namespace'].copy()
        d['query_ids'] = [query]; d['candidate_ids'] = [candidate]
        d['data']['inline'] = {'row_ids': [query], 'column_ids': [candidate], 'values': [[1]]}
        outputs.append(load_comparison_input(d))
    base = compare_results(outputs)
    layer = profile_layer(base)
    layer.update(layer_id='layer ' + HOSTILE, units='units ' + HOSTILE, transform='transform ' + HOSTILE)
    n = len(base.dataset['observation_ids'])
    for f in layer['features']:
        f.update(values=list(range(n)), observed=[i != 1 for i in range(n)], annotations=HOSTILE)
    return compare_results(outputs, profiles=ProfileData([layer])), query, candidate, layer['layer_id']


def assert_safe_svg(case, path):
    root = ET.parse(path).getroot()
    case.assertEqual(root.tag, SVG + 'svg')
    for node in root.iter():
        case.assertNotIn(node.tag.rsplit('}', 1)[-1], ('script', 'foreignObject', 'a', 'image'))
        for key, value in node.attrib.items():
            case.assertFalse(key.startswith('on'))
            if key.rsplit('}', 1)[-1] == 'href':
                case.assertTrue(value.startswith('#'), value)
    return root, root.find(SVG + 'desc').text


class FigureCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.result = b1_result()

    def export(self, result=None, name='figure.svg', **kwargs):
        opts = dict(query_id='M01', candidate_id='P01', layer_id='measured', output=self.root/name)
        opts.update(kwargs)
        return export_query_figure(result or self.result, **opts)

    def test_actual_svg_pdf_hostile_literals_same_and_cross_modality(self):
        import matplotlib as mpl
        for same in (False, True):
            r, q, c, layer = hostile_result(same)
            with mpl.rc_context({'text.usetex': True, 'text.parse_math': True}):
                path = self.export(r, name=f'{same}.svg', query_id=q, candidate_id=c, layer_id=layer, notes=HOSTILE)
                self.assertTrue(mpl.rcParams['text.usetex'])
                root, caption = assert_safe_svg(self, path)
                for value in (q, c, layer, 'units ' + HOSTILE, 'transform ' + HOSTILE, 'User notes: ' + HOSTILE):
                    self.assertIn(value, caption)
                self.assertIn('not model attribution', caption)
                self.assertIn('finite originally unobserved: 1', caption)
                texts = '\n'.join(n.text or '' for n in root.iter(SVG + 'text'))
                self.assertIn(q, texts)
                pdf = self.export(r, name=f'{same}.pdf', query_id=q, candidate_id=c, layer_id=layer, notes=HOSTILE)
                self.assertTrue(pdf.read_bytes().startswith(b'%PDF-'))
                self.assertGreater(pdf.stat().st_size, 5000)
                # PDF Subject is exact UTF-16BE, independent of unavailable PDF readers.
                encoded = HOSTILE.encode('utf-16-be')
                escaped = encoded.replace(b'\\', b'\\\\').replace(b'(', b'\\(').replace(b')', b'\\)')
                self.assertTrue(escaped in pdf.read_bytes(), 'Exact literal caption must survive PDF string escaping')

    def test_masks_counts_diagnostics_groups_and_real_artist_cohorts(self):
        from matplotlib.figure import Figure
        save = Figure.savefig
        seen = []
        def inspect(fig, *args, **kwargs):
            scatter, profile = fig.axes
            seen.append((list(scatter.collections[0].get_offsets()),
                         [len(c.get_offsets()) for c in profile.collections]))
            return save(fig, *args, **kwargs)
        with patch.object(Figure, 'savefig', inspect):
            path = self.export(color='condition', group='condition', h=1, omission=True, order='metadata')
        _, caption = assert_safe_svg(self, path)
        self.assertEqual([tuple(v) for v in seen[0][0]], [(1, 1), (2, 2), (4, 4), (6, 6)])
        self.assertEqual(seen[0][1], [4, 1, 4, 1])
        for value in ('required samples: 6', 'jointly observed finite: 4', 'query observed finite: 4',
                      'finite originally unobserved: 1', 'explicit_original', 'marginal group summary',
                      '"omission": true', '"h": 1', 'Metadata color key: condition', 'Pool policy:'):
            self.assertIn(value, caption)

    def test_exact_multiline_caption_and_missing_renderer_cleanup(self):
        notes = 'line one\rline two\nline three\t$literal$'
        _, caption = assert_safe_svg(self, self.export(notes=notes))
        self.assertIn('User notes: ' + notes, caption)
        with patch.dict(sys.modules, {'matplotlib': None}):
            with self.assertRaisesRegex(ComparisonValidationError, 'Matplotlib is required'):
                self.export(name='missing.svg')
        self.assertFalse((self.root/'missing.svg').exists())
        self.assertFalse(list(self.root.glob('.valpas-figure-*')))

    def test_no_joint_values_exports_marginal_profiles_not_imputed_scatter(self):
        layer = profile_layer(self.result)
        for f in layer['features']:
            f['observed'] = [False] * 6
        r = replace(self.result, profiles=ProfileData([layer]))
        _, caption = assert_safe_svg(self, self.export(r))
        self.assertIn('jointly observed finite: 0', caption)
        self.assertIn('no_jointly_observed_finite_values', caption)

    def test_full_bundle_outside_browser_scope_source_removal_and_cli(self):
        source = self.root/'sources'; shutil.copytree(FIXTURE, source)
        result = compare_results(load_manifest(source/'manifest-with-b1.json'))
        settings = ReportSettings(query_ids=('M01',), max_interactive_depth=1, omit_metadata=True)
        bundle = write_comparison(result, self.root/'bundle', report_settings=settings)
        shutil.rmtree(source)
        self.assertFalse(build_report_payload(load_comparison_bundle(bundle))['layers'])
        layer = result.profiles.layers[0]['layer_id']
        q = next(q for o in result.outputs for q in o.query_ids if q != 'M01')
        c = result.outputs[0].candidate_ids[-1]
        self.export(bundle, query_id=q, candidate_id=c, layer_id=layer)
        command = [sys.executable, '-m', 'valpas.cli', 'export-query', '--bundle', str(bundle),
                   '--query', q, '--candidate', c, '--layer', layer, '--output', str(self.root/'cli.pdf')]
        proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue((self.root/'cli.pdf').read_bytes().startswith(b'%PDF-'))
        proc = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 2)
        self.assertIn('export-query:', proc.stderr); self.assertNotIn('Traceback', proc.stderr)

    def test_path_safety_owned_bundle_symlink_source_and_staged_failure(self):
        bundle = write_comparison(self.result, self.root/'bundle')
        source = self.root/'source.svg'; source.write_text('source')
        link = self.root/'link.svg'; link.symlink_to(source)
        directory = self.root/'alias'; directory.symlink_to(self.root, target_is_directory=True)
        for output in (source, link, directory/'new.svg', self.root/'x'/'..'/'new.svg',
                       self.root/'missing'/'new.svg', self.root/'bad.png', bundle/'extra.svg'):
            with self.subTest(output=output), self.assertRaises((ValueError, OSError)):
                self.export(output=output)
        self.assertEqual(source.read_text(), 'source')
        with self.assertRaisesRegex(ValueError, 'consumed source'):
            self.export(replace(self.result, protected_sources=(str(self.root/'reserved.svg'),)), name='reserved.svg')
        recorded = replace(self.result, source_fingerprints=({'path': str(self.root/'removed-source.svg')},))
        with self.assertRaisesRegex(ValueError, 'consumed source'):
            self.export(recorded, name='removed-source.svg')
        with patch('valpas.comparison.figures._render', side_effect=RuntimeError('renderer failed')):
            with self.assertRaisesRegex(RuntimeError, 'renderer failed'):
                self.export()
        self.assertFalse((self.root/'figure.svg').exists())
        self.assertFalse(list(self.root.glob('.valpas-figure-*')))
        # Simulate another writer arriving between validation and publication.
        def racer(*args):
            (self.root/'figure.svg').write_text('other writer')
        with patch('valpas.comparison.figures._render', side_effect=racer):
            with self.assertRaises(FileExistsError): self.export()
        self.assertEqual((self.root/'figure.svg').read_text(), 'other writer')
        self.assertFalse(list(self.root.glob('.valpas-figure-*')))

    def test_actionable_failures_before_renderer(self):
        unavailable = profile_layer(self.result); unavailable['mask_source'] = 'unavailable'
        for f in unavailable['features']: f['observed'] = None
        missing = profile_layer(self.result); missing['features'] = missing['features'][1:]
        cases = [(replace(self.result, profiles=None, diagnostic_requests=()), {}, 'no profile'),
                 (self.result, {'layer_id': 'missing'}, 'unavailable layer'),
                 (self.result, {'query_id': 'missing'}, 'outside declared'),
                 (replace(self.result, profiles=ProfileData([unavailable])), {}, 'original_mask_unavailable'),
                 (replace(self.result, profiles=ProfileData([missing])), {}, 'missing_feature'),
                 (self.result, {'color': 'missing'}, 'metadata field unavailable'),
                 (self.result, {'group': 'age'}, 'categorical'),
                 (self.result, {'h': True}, 'integer'),
                 (self.result, {'notes': '\x00'}, 'XML')]
        for r, kw, message in cases:
            with self.subTest(message=message), patch('valpas.comparison.figures._render') as render:
                with self.assertRaisesRegex(ComparisonValidationError, message): self.export(r, **kw)
                render.assert_not_called()

    def test_session_decision_context_strict_binding_and_no_schema_change(self):
        session = chosen(self.result).add_decision(decision_id='d1', decision='investigate',
            rationale=HOSTILE, timestamp='2026-11-19T00:00:00Z')
        path = self.export(session=session, decision_id='d1')
        _, caption = assert_safe_svg(self, path)
        self.assertIn(HOSTILE.replace('"', '\\"').replace('\\notacommand', '\\\\notacommand'), caption)
        self.assertIn('"decision_id": "d1"', caption)
        for opts in ({'candidate_id': 'P02'}, {'h': 2}, {'decision_id': 'absent'}):
            with self.assertRaises(ValueError): self.export(name='reject.svg', session=session, **opts)
        with self.assertRaises(ValueError):
            self.export(replace(self.result, sample_metadata=None), name='changed.svg', session=session)

    def test_session_bundle_old_assets_reload_and_payload_tamper_rejected(self):
        from valpas.comparison import browser
        original = browser.asset_text
        with patch.object(browser, 'asset_text', side_effect=lambda name: original(name) + ('\n// old asset revision' if name == 'dashboard.js' else '')):
            bundle = write_comparison(self.result, self.root/'old', initial_session=chosen(self.result))
        self.assertIsNotNone(load_comparison_bundle(bundle).initial_session)
        self.export(bundle)
        # Even with matching inventory hashes, required session fields cannot vanish.
        path = bundle/'report_payload.json'; payload = json.loads(path.read_text())
        payload.pop('session_content_id'); path.write_text(json.dumps(payload))
        marker = bundle/'comparison.json'; doc = json.loads(marker.read_text())
        doc['inventory']['report_payload.json'] = digest_record(path)
        marker.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): load_comparison_bundle(bundle)


class FigureIsolationCase(SubprocessCase):
    def test_help_and_public_api_are_lightweight(self):
        self.run_python(IMPORT_GUARD + '''
from valpas.comparison import export_query_figure
import runpy
sys.argv=['valpas','export-query','--help']
try: runpy.run_module('valpas.cli',run_name='__main__')
except SystemExit as exc: assert exc.code == 0
''' + IMPORT_ASSERTIONS)

    def test_actual_export_blocks_training_imports(self):
        fixture = str(FIXTURE/'manifest-with-profiles.json')
        self.run_python('''
import importlib.abc, sys, tempfile
from pathlib import Path
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self, fullname, path=None, target=None):
  if fullname.startswith(('torch','valpas._core','valpas.valpas_core','valpas.io','sklearn')):
   raise AssertionError('Training import: '+fullname)
sys.meta_path.insert(0,Guard())
from valpas.comparison import compare_results, load_manifest, export_query_figure
r=compare_results(load_manifest(''' + repr(fixture) + '''))
with tempfile.TemporaryDirectory() as tmp:
 export_query_figure(r,query_id='M01',candidate_id='P01',layer_id=r.profiles.layers[0]['layer_id'],output=Path(tmp)/'figure.svg')
''')

    def test_cli_delegates_public_api(self):
        self.run_python('''
import sys
from unittest.mock import patch
from valpas import cli
with patch('valpas.comparison.export_query_figure',return_value='figure.svg') as export:
 sys.argv=['valpas','export-query','--bundle','bundle','--query','q','--candidate','c','--layer','l','--output','figure.svg']
 cli.main()
 assert export.call_count == 1
 assert export.call_args.kwargs['query_id'] == 'q'
 assert export.call_args.kwargs['candidate_id'] == 'c'
''')


if __name__ == '__main__': unittest.main()
