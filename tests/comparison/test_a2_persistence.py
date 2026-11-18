"""A2 identity, durable persistence, and publication safety; no scoring/models."""
import copy
import csv
from dataclasses import replace
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from test_a1_contracts import descriptor, prefix_descriptor, table_descriptor, FIXTURE
from valpas.comparison import (ComparisonSettings, ComparisonValidationError,
    compare_results, load_comparison_input, load_manifest, write_comparison,
    load_comparison_bundle, export_comparison_inputs)
from valpas.comparison.models import thaw
from valpas.comparison import report


def simple_result():
    return compare_results([load_comparison_input(descriptor(x)) for x in ('a', 'b')],
                           ComparisonSettings(depths=(1, 2, 5)))


class PersistenceCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def assert_tables_equal(self, left, right):
        self.assertEqual(left.comparison_id, right.comparison_id)
        for name in left.table_names:
            self.assertEqual(list(left.iter_table(name)), list(right.iter_table(name)), name)

    def marker(self, path):
        return json.loads((path / 'comparison.json').read_text())

    def edit_marker(self, path, mutate):
        m = self.marker(path)
        mutate(m)
        (path / 'comparison.json').write_text(json.dumps(m))

    def refresh_inventory(self, path, name):
        raw = (path / name).read_bytes()
        self.edit_marker(path, lambda m: m['inventory'].__setitem__(name, {
            'sha256': hashlib.sha256(raw).hexdigest(), 'size_bytes': len(raw)}))

    def test_roundtrip_all_tables_and_exact_csv_cells(self):
        result = compare_results(load_manifest(FIXTURE / 'manifest.json'))
        path = write_comparison(result, self.root / 'bundle')
        loaded = load_comparison_bundle(path)
        self.assert_tables_equal(result, loaded)
        self.assertEqual(result.source_fingerprints, loaded.source_fingerprints)
        m = self.marker(path)
        self.assertTrue(m['complete'])
        self.assertEqual(m['scope']['analysis'], 'all_declared_queries_under_pool_policy')
        self.assertFalse(m['scope']['html'])
        self.assertEqual(set(m['inventory']) | {'comparison.json'}, {p.name for p in path.iterdir()})
        for name, spec in m['tables'].items():
            file = path / spec['path']
            opener = gzip.open if file.suffix == '.gz' else open
            with opener(file, 'rt', encoding='utf-8', newline='') as handle:
                reader = csv.DictReader(handle)
                rows = [{k: json.loads(v) for k, v in row.items()} for row in reader]
            self.assertEqual(rows, list(result.iter_table(name)), name)
            self.assertEqual(len(rows), spec['rows'])
        self.assertFalse(list(path.glob('*.html')))

    def test_relocated_bundle_reloads_without_original_sources(self):
        source = self.root / 'source'
        shutil.copytree(FIXTURE, source)
        result = compare_results(load_manifest(source / 'manifest.json'))
        path = write_comparison(result, self.root / 'bundle')
        moved = self.root / 'moved'
        path.rename(moved)
        shutil.rmtree(source)
        self.assert_tables_equal(result, load_comparison_bundle(moved))

    def test_all_representation_roundtrips(self):
        factories = [descriptor, table_descriptor, prefix_descriptor]
        for i, factory in enumerate(factories):
            with self.subTest(factory=factory.__name__):
                outputs = [load_comparison_input(factory(oid=x)) for x in ('a', 'b')]
                result = compare_results(outputs, ComparisonSettings(depths=(1, 2, 5)))
                self.assert_tables_equal(result, load_comparison_bundle(
                    write_comparison(result, self.root / str(i))))
        d = descriptor('legacy')
        d['representation'] = 'legacy_score_count'
        d['count_semantics'] = 'joint observations'
        d['data']['inline']['values'] = [['0.125000000000001:7', '0.8:6', '0.1:4']]
        result = compare_results([load_comparison_input(d), load_comparison_input(descriptor('b'))])
        self.assert_tables_equal(result, load_comparison_bundle(write_comparison(result, self.root / 'legacy')))
        outputs = []
        for oid in ('a', 'b'):
            d = descriptor(oid)
            d['label'] = '</script><script>not executable</script>'
            d['query_ids'] = [' q,\n"Ω" ']
            d['candidate_ids'] = ['001', '=SUM(A1:A2)', ' 01 ']
            d['data']['inline'] = {'row_ids': d['query_ids'], 'column_ids': d['candidate_ids'],
                                   'values': [[0.12345678901234567, -0.0, None]]}
            outputs.append(load_comparison_input(d))
        result = compare_results(outputs)
        self.assert_tables_equal(result, load_comparison_bundle(write_comparison(result, self.root / 'exact-ids')))

    def test_source_hashes_are_consumed_bytes_not_reopened_files(self):
        source = self.root / 'source'
        shutil.copytree(FIXTURE, source)
        manifest = load_manifest(source / 'manifest.json')
        result = compare_results(manifest)
        self.assertEqual(len(result.source_fingerprints), 4)
        for f in result.source_fingerprints:
            raw = Path(f['path']).read_bytes()
            self.assertEqual(f['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(f['size_bytes'], len(raw))
        before = result.comparison_id
        (source / 'pearson-run.csv').write_text('subsequently changed source')
        path = write_comparison(compare_results(manifest), self.root / 'bundle')
        self.assertEqual(load_comparison_bundle(path).comparison_id, before)
        self.assertEqual(self.marker(path)['source_fingerprints'], thaw(result.source_fingerprints))

    def test_identity_invariant_under_transport_order_and_descriptive_metadata(self):
        original = [descriptor('a'), descriptor('b')]
        first = compare_results([load_comparison_input(d) for d in original], ComparisonSettings(depths=(1, 2)))
        changed = copy.deepcopy(original)
        for d in changed:
            d['candidate_ids'].reverse()
            d['identity']['observation_ids'].reverse()
            d['data']['inline']['column_ids'].reverse()
            d['data']['inline']['values'][0].reverse()
            d['label'] = 'descriptive new label'
            d['provenance']['source'] = '/different/path/with/timestamp'
        second = compare_results([load_comparison_input(d) for d in reversed(changed)], ComparisonSettings(depths=(2, 1)))
        self.assertEqual(first.comparison_id, second.comparison_id)
        for directory in ('first', 'second'):
            shutil.copytree(FIXTURE, self.root / directory)
        a = compare_results(load_manifest(self.root / 'first' / 'manifest.json'))
        b = compare_results(load_manifest(self.root / 'second' / 'manifest.json'))
        self.assertEqual(a.comparison_id, b.comparison_id)
        self.assertNotEqual(a.source_fingerprints, b.source_fingerprints)
        for i in range(2):
            self.assertEqual(self.marker(write_comparison(first, self.root / ('out' + str(i))))['comparison_id'], first.comparison_id)

    def test_identity_changes_for_values_statuses_counts_and_settings(self):
        outputs = []
        for oid in ('a', 'b'):
            d = descriptor(oid)
            d['count_semantics'] = 'joint observations'
            outputs.append(load_comparison_input(d))
        base = compare_results(outputs, ComparisonSettings(depths=(1, 2, 5)))
        for field, value in [('score', 0.11), ('status', 'unscored'), ('count', 8)]:
            outputs = list(base.outputs)
            pairs = dict(outputs[0].pairs)
            old = pairs[('q', 'c')]
            pairs[('q', 'c')] = replace(old, **({field: value, 'score': None, 'reason': 'not measured'} if field == 'status' else {field: value}))
            outputs[0] = replace(outputs[0], pairs=pairs)
            self.assertNotEqual(compare_results(outputs, base.settings).comparison_id, base.comparison_id)
        for settings in (ComparisonSettings(depths=(1,)), ComparisonSettings(pool_policy='common', depths=(1, 2, 5)),
                         ComparisonSettings(exclude_self=False, depths=(1, 2, 5))):
            self.assertNotEqual(compare_results(base.outputs, settings).comparison_id, base.comparison_id)

    def test_completion_schema_inventory_and_table_corruption_rejected(self):
        mutations = [lambda m: m.update(complete=False), lambda m: m.update(schema_version=2),
                     lambda m: m.update(software_version='unsupported-version'),
                     lambda m: m['normalized_inputs'][0]['descriptor'].update(data=None),
                     lambda m: m.update(kind='valpas-comparison-input'),
                     lambda m: m['table_schema']['agreement'].update(columns=['wrong']),
                     lambda m: m['normalized_inputs'][0].update(path='../source.json'),
                     lambda m: m['tables']['agreement'].update(rows=True),
                     lambda m: m.update(comparison_id='wrong'),
                     lambda m: m.update(settings=None)]
        for i, mutate in enumerate(mutations):
            with self.subTest(i=i):
                path = write_comparison(simple_result(), self.root / str(i))
                self.edit_marker(path, mutate)
                with self.assertRaises(ComparisonValidationError):
                    load_comparison_bundle(path)
        path = write_comparison(simple_result(), self.root / 'badtable')
        with (path / 'agreement.csv').open('a') as handle:
            handle.write('corruption\n')
        with self.assertRaisesRegex(ComparisonValidationError, 'checksum'):
            load_comparison_bundle(path)
        self.refresh_inventory(path, 'agreement.csv')
        with self.assertRaisesRegex(ComparisonValidationError, 'row inventory'):
            load_comparison_bundle(path)

    def test_normalized_values_checked_even_after_inventory_refresh(self):
        path = write_comparison(simple_result(), self.root / 'bundle')
        name = 'normalized-0000.jsonl.gz'
        with gzip.open(path / name, 'rt') as handle:
            rows = [json.loads(line) for line in handle]
        rows[0]['score'] = 0.123456789012345
        with gzip.open(path / name, 'wt') as handle:
            handle.writelines(json.dumps(row) + '\n' for row in rows)
        self.refresh_inventory(path, name)
        with self.assertRaisesRegex(ComparisonValidationError, 'identity mismatch'):
            load_comparison_bundle(path)

    def test_default_refusal_explicit_owned_overwrite_and_loaded_source_protection(self):
        result = simple_result()
        path = write_comparison(result, self.root / 'bundle')
        old = (path / 'comparison.json').read_bytes()
        with self.assertRaisesRegex(ComparisonValidationError, 'existing destination'):
            write_comparison(result, path)
        self.assertEqual((path / 'comparison.json').read_bytes(), old)
        write_comparison(result, path, overwrite=True)
        loaded = load_comparison_bundle(path)
        self.assert_tables_equal(result, loaded)
        with self.assertRaisesRegex(ComparisonValidationError, 'consumed source'):
            write_comparison(loaded, path, overwrite=True)
        self.assert_tables_equal(result, load_comparison_bundle(write_comparison(loaded, self.root / 'copy')))

    def test_unrelated_empty_input_partial_foreign_and_symlink_destinations_refused(self):
        result = simple_result()
        for name in ('empty', 'unrelated', 'partial'):
            path = self.root / name
            path.mkdir()
            if name != 'empty':
                (path / 'keep.txt').write_text('must survive')
            with self.assertRaises(ComparisonValidationError):
                write_comparison(result, path, overwrite=True)
            self.assertTrue(path.exists())
        inputs = export_comparison_inputs(result.outputs, self.root / 'inputs')
        with self.assertRaises(ComparisonValidationError):
            write_comparison(result, inputs, overwrite=True)
        path = write_comparison(result, self.root / 'foreign')
        (path / 'keep.txt').write_text('must survive')
        with self.assertRaisesRegex(ComparisonValidationError, 'foreign'):
            write_comparison(result, path, overwrite=True)
        self.assertEqual((path / 'keep.txt').read_text(), 'must survive')
        link = self.root / 'link'
        link.symlink_to(path, target_is_directory=True)
        with self.assertRaisesRegex(ComparisonValidationError, 'symlink'):
            write_comparison(result, link, overwrite=True)
        with self.assertRaisesRegex(ComparisonValidationError, 'traversal'):
            write_comparison(result, self.root / 'other' / '..' / 'new')

    def test_input_containment_and_symlink_member_rejected(self):
        source = self.root / 'source'
        shutil.copytree(FIXTURE, source)
        result = compare_results(load_manifest(source / 'manifest.json'))
        with self.assertRaisesRegex(ComparisonValidationError, 'consumed source'):
            write_comparison(result, source, overwrite=True)
        path = write_comparison(result, self.root / 'bundle')
        member = path / 'README.md'
        external = self.root / 'external'
        member.rename(external)
        member.symlink_to(external)
        with self.assertRaisesRegex(ComparisonValidationError, 'symlink'):
            write_comparison(result, path, overwrite=True)
        self.assertTrue(external.exists())

    def test_staging_failure_cleans_new_output_and_preserves_existing(self):
        result = simple_result()
        existing = write_comparison(result, self.root / 'existing')
        before = {p.name: p.read_bytes() for p in existing.iterdir()}
        for path in (self.root / 'new', existing):
            with patch.object(report, '_write_tables', side_effect=OSError('injected disk failure')):
                with self.assertRaisesRegex(ComparisonValidationError, 'injected disk failure'):
                    write_comparison(result, path, overwrite=True)
        self.assertFalse((self.root / 'new').exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in existing.iterdir()})
        self.assertFalse(list(self.root.glob('.*partial-*')))

    def test_publication_failure_rolls_back_existing_and_cleans_reservation(self):
        result = simple_result()
        existing = write_comparison(result, self.root / 'existing')
        before = {p.name: p.read_bytes() for p in existing.iterdir()}
        real_replace = report.os.replace
        def fail_publish(source, destination):
            if '.partial-' in Path(source).name:
                raise OSError('injected rename failure')
            return real_replace(source, destination)
        for path in (self.root / 'new', existing):
            with patch.object(report.os, 'replace', side_effect=fail_publish):
                with self.assertRaisesRegex(ComparisonValidationError, 'injected rename failure'):
                    write_comparison(result, path, overwrite=True)
        self.assertFalse((self.root / 'new').exists())
        self.assertEqual(before, {p.name: p.read_bytes() for p in existing.iterdir()})
        self.assertEqual({p.name for p in self.root.iterdir()}, {'existing'})

    def test_bounded_multquery_export_smoke_no_expanded_result_tables(self):
        outputs = []
        for oid in ('a', 'b', 'c'):
            d = descriptor(oid)
            d['query_ids'] = ['q' + str(i) for i in range(20)]
            d['candidate_ids'] = ['c' + str(i) for i in range(100)]
            d['data']['inline'] = {'row_ids': d['query_ids'], 'column_ids': d['candidate_ids'],
                                   'values': [[i / 100 for i in range(100)] for _ in range(20)]}
            outputs.append(load_comparison_input(d))
        result = compare_results(outputs, ComparisonSettings(depths=(5, 10)))
        self.assertNotIn('candidate_ranks', result.summaries)
        self.assertNotIn('run_recurrence', result.summaries)
        with self.assertRaises(ComparisonValidationError):
            result.materialize_table('candidate_ranks', max_rows=100)
        with patch.object(type(result), 'materialize_table', side_effect=AssertionError('must stream')):
            path = write_comparison(result, self.root / 'smoke')
            loaded = load_comparison_bundle(path)
        self.assertEqual(self.marker(path)['tables']['candidate_ranks']['rows'], 6000)
        self.assertEqual(loaded.comparison_id, result.comparison_id)


    def test_attested_implicit_dataset_roundtrip(self):
        outputs, claims = [], []
        for oid in ('a', 'b'):
            d = descriptor(oid)
            context = d['identity']['context']
            d['identity']['context'] = None
            claims.append({'output_id': oid, 'field': 'context',
                           'claimed_value': context, 'statement': 'same synthetic context'})
            outputs.append(load_comparison_input(d))
        result = compare_results(outputs, ComparisonSettings(attestations=tuple(claims)))
        self.assertIsNotNone(result.dataset['context'])
        self.assert_tables_equal(result, load_comparison_bundle(write_comparison(result, self.root / 'attested')))

    def test_common_excluded_query_keeps_all_native_ranks(self):
        a, b = descriptor('a'), descriptor('b')
        a['query_ids'].append('extra')
        a['data']['inline']['row_ids'].append('extra')
        a['data']['inline']['values'].append([0.1, 0.2, 0.3])
        result = compare_results([load_comparison_input(a), load_comparison_input(b)],
                                 ComparisonSettings(pool_policy='common'))
        rows = [r for r in result.iter_table('candidate_ranks') if r['query_id'] == 'extra']
        self.assertEqual(len(rows), 3)
        self.assertEqual([r['native_rank'] for r in rows], [3, 2, 1])
        self.assertTrue(all(r['active_rank'] is None and r['active_status'] == 'excluded_query' for r in rows))
        self.assert_tables_equal(result, load_comparison_bundle(write_comparison(result, self.root / 'common')))

    def test_overwrite_rejects_semantically_corrupt_owned_bundle(self):
        result = simple_result()
        path = write_comparison(result, self.root / 'bundle')
        self.edit_marker(path, lambda m: m.update(settings=None))
        before = (path / 'comparison.json').read_bytes()
        with self.assertRaises(ComparisonValidationError):
            write_comparison(result, path, overwrite=True)
        self.assertEqual(before, (path / 'comparison.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
