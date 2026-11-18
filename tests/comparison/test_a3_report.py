"""Release A offline payload, profile contracts, durability and publication guards."""
import copy
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

from test_a1_contracts import FIXTURE
from valpas.comparison import (ComparisonSettings, ComparisonValidationError, ProfileData,
    ReportSettings, compare_results, load_manifest, load_profile_data,
    load_comparison_bundle, write_comparison)
from valpas.comparison.browser import build_report_payload, render_report, asset_text, safe_json
from valpas.comparison.models import thaw
from valpas.comparison.profiles import feature_coverage, pair_profile


def fixture_result():
    return compare_results(load_manifest(FIXTURE / 'manifest.json'))


def profile_layer(result=None):
    r = result or fixture_result()
    dataset = thaw(r.dataset)
    features = []
    for role in ('query', 'candidate'):
        for fid in sorted(set().union(*(set(getattr(o, role + '_ids')) for o in r.outputs))):
            features.append({'namespace': dataset[role + '_namespace'], 'feature_id': fid,
                             'label': 'Shared label', 'annotations': 'synthetic annotation',
                             'values': [1, 2, 99, 4, None, 6],
                             'observed': [True, True, False, True, False, True]})
    return {'layer_id': 'measured', 'dataset': dataset,
            'orientation': 'feature_rows_observation_columns',
            'observation_ids': list(dataset['observation_ids']), 'units': 'synthetic abundance',
            'transform': 'none', 'provenance': 'Synthetic values, not the scoring layer',
            'raw_unimputed': False, 'mask_source': 'explicit_original',
            'subset_extra_observations': False,
            'algorithm_layers': {o.output_id: 'different' for o in r.outputs}, 'features': features}


def profiled_result(layer=None):
    r = fixture_result()
    return compare_results(r.outputs, r.settings, dataset=r.dataset,
                           profiles=ProfileData([layer or profile_layer(r)]))


class ProfilesCase(unittest.TestCase):
    def test_explicit_mask_independent_of_imputation(self):
        r = profiled_result()
        row = next(r.iter_table('feature_coverage'))
        self.assertEqual((row['observed_count'], row['missing_count'], row['finite_unobserved_count']), (4, 2, 1))
        p = pair_profile(r.profiles.layers[0], r.dataset, 'M01', 'P01')
        self.assertEqual(p['joint_indices'], [0, 1, 3, 5])
        self.assertEqual(p['query_unobserved_indices'], [2])
        self.assertEqual(p['joint_observed_count'], 4)

    def test_raw_finite_requires_explicit_raw_declaration(self):
        l = profile_layer(); l['mask_source'] = 'raw_finite'
        for f in l['features']: f['observed'] = None
        with self.assertRaisesRegex(ComparisonValidationError, 'raw unimputed'):
            ProfileData([l])
        l['raw_unimputed'] = True
        r = profiled_result(l)
        self.assertEqual(next(r.iter_table('feature_coverage'))['observed_count'], 5)

    def test_unknown_masks_have_unknown_counts_and_disabled_scatter(self):
        l = profile_layer(); l['mask_source'] = 'unavailable'
        for f in l['features']: f['observed'] = None
        r = profiled_result(l)
        row = next(r.iter_table('feature_coverage'))
        self.assertIsNone(row['observed_count'])
        self.assertEqual(row['reason'], 'original_mask_unavailable')
        self.assertEqual(pair_profile(r.profiles.layers[0], r.dataset, 'M01', 'P01')['joint_indices'], [])
        self.assertTrue(all(v['observed'] is None for v in r.iter_table('profile_values')))

    def test_alignment_exact_reorder_extra_and_missing_cohort(self):
        l = profile_layer()
        l['observation_ids'].reverse()
        for f in l['features']:
            f['values'].reverse(); f['observed'].reverse()
        r = profiled_result(l)
        p = pair_profile(r.profiles.layers[0], r.dataset, 'M01', 'P01')
        self.assertEqual(p['joint_indices'], [5, 4, 2, 0])
        l['observation_ids'].append('EXTRA')
        for f in l['features']:
            f['values'].append(42); f['observed'].append(True)
        with self.assertRaisesRegex(ComparisonValidationError, 'extra observations'):
            profiled_result(l)
        l['subset_extra_observations'] = True
        row = next(profiled_result(l).iter_table('feature_coverage'))
        self.assertEqual(row['excluded_observation_ids'], ['EXTRA'])
        self.assertEqual(row['observed_count'], 4)
        l['observation_ids'][0] = 'NOT-S06'
        r = profiled_result(l)
        self.assertEqual(next(r.iter_table('feature_coverage'))['reason'], 'missing_required_observations')
        self.assertEqual(pair_profile(r.profiles.layers[0], r.dataset, 'M01', 'P01')['joint_indices'], [])

    def test_missing_feature_constant_near_empty(self):
        l = profile_layer(); l['features'] = [f for f in l['features'] if f['feature_id'] != 'P01']
        for f in l['features']:
            f['values'] = [1, 1, None, None, None, None]
            f['observed'] = [True, True, False, False, False, False]
        r = profiled_result(l)
        rows = list(r.iter_table('feature_coverage'))
        self.assertEqual(next(v for v in rows if v['feature_id']=='P01')['reason'], 'missing_feature')
        row = next(v for v in rows if v['feature_id']=='M01')
        self.assertTrue(row['constant']); self.assertTrue(row['near_empty'])
        self.assertEqual(pair_profile(r.profiles.layers[0], r.dataset, 'M01', 'P01')['reason'], 'missing_feature')

    def test_strict_layer_contract_rejections(self):
        mutations = [lambda l:l.update(orientation='observations_by_features'),
                     lambda l:l.update(raw_unimputed=True),
                     lambda l:l['features'][0]['values'].append(1),
                     lambda l:l['features'][0]['values'].__setitem__(0, float('nan')),
                     lambda l:l['features'][0]['observed'].__setitem__(0, 1),
                     lambda l:l['features'].append(copy.deepcopy(l['features'][0])),
                     lambda l:l['observation_ids'].__setitem__(0, l['observation_ids'][1]),
                     lambda l:l['algorithm_layers'].clear(),
                     lambda l:l['dataset'].update(dataset_id='other'),
                     lambda l:l.update(mask_source='auto')]
        for change in mutations:
            l=profile_layer(); change(l)
            with self.subTest(change=change), self.assertRaises(ComparisonValidationError):
                profiled_result(l)

    def test_profile_values_are_stored_once_per_layer_feature(self):
        r=profiled_result(); p=build_report_payload(r, ReportSettings(max_interactive_depth=2))
        self.assertEqual(len(list(r.iter_table('profile_values'))), 30)
        self.assertEqual(len(p['layers'][0]['features']), 5)
        for d in p['details'].values():
            self.assertTrue(all('values' not in v for v in d['profiles']))


class ReportCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_default_html_and_explicit_tables_only(self):
        r=profiled_result()
        for only in (False,True):
            p=write_comparison(r,self.root/str(only),tables_only=only)
            self.assertEqual((p/'report.html').exists(),not only)
            loaded=load_comparison_bundle(p)
            for table in r.table_names:
                self.assertEqual(list(r.iter_table(table)),list(loaded.iter_table(table)))

    def test_analysis_identity_and_tables_independent_of_report_scope(self):
        r=profiled_result(); original={n:list(r.iter_table(n)) for n in r.table_names}
        a=build_report_payload(r,ReportSettings(query_ids=('M01',),max_interactive_depth=1,pinned_candidate_ids=('P03',)))
        b=build_report_payload(r,ReportSettings(max_interactive_depth=3))
        self.assertEqual(a['comparison_id'],b['comparison_id'])
        self.assertEqual(a['all_query_ids'],b['all_query_ids'])
        self.assertEqual(set(a['details']),{'M01'})
        self.assertIn('P03',a['details']['M01']['candidate_ids'])
        self.assertEqual(original,{n:list(r.iter_table(n)) for n in r.table_names})
        self.assertEqual([v for v in a['agreement'] if v['requested_depth']==1], [v for v in b['agreement'] if v['requested_depth']==1])

    def test_embedded_metrics_ranks_and_recurrence_equal_engine(self):
        r=profiled_result(); p=build_report_payload(r,ReportSettings(max_interactive_depth=5))
        self.assertEqual([v for v in p['agreement'] if v['requested_depth'] in r.settings.depths],list(r.iter_table('agreement')))
        ranks=list(r.iter_table('candidate_ranks')); recurrence=list(r.iter_table('run_recurrence'))
        for q,d in p['details'].items():
            self.assertEqual(d['ranks'],[v for v in ranks if v['query_id']==q and v['candidate_id'] in d['candidate_ids']])
            for v in d['recurrence']:
                if v['requested_depth'] in r.settings.depths: self.assertIn(v,recurrence)

    def test_saved_profiles_reload_and_reexport_after_sources_deleted(self):
        source=self.root/'source'; shutil.copytree(FIXTURE,source)
        (source/'profiles.json').write_text(json.dumps({'schema_version':1,'layers':[profile_layer()]}))
        m=json.loads((source/'manifest.json').read_text()); m['profiles']={'path':'profiles.json'}
        m['report']={'query_ids':['M01'],'max_interactive_depth':2}
        (source/'manifest.json').write_text(json.dumps(m))
        r=compare_results(load_manifest(source/'manifest.json'))
        out=write_comparison(r,self.root/'out'); shutil.rmtree(source)
        loaded=load_comparison_bundle(out)
        again=write_comparison(loaded,self.root/'again')
        self.assertEqual((out/'report.html').read_bytes(),(again/'report.html').read_bytes())
        self.assertEqual(list(r.iter_table('profile_values')),list(loaded.iter_table('profile_values')))
        self.assertEqual(loaded.report_settings.query_ids,('M01',))

    def test_payload_budget_rejects_before_publish_and_preserves_old_bundle(self):
        r=fixture_result(); out=write_comparison(r,self.root/'out')
        before={p.name:p.read_bytes() for p in out.iterdir()}
        for destination,overwrite in ((out,True),(self.root/'new',False)):
            with self.assertRaisesRegex(ComparisonValidationError,'before HTML wrapping'):
                write_comparison(r,destination,overwrite=overwrite,report_settings=ReportSettings(max_payload_bytes=1))
        self.assertEqual(before,{p.name:p.read_bytes() for p in out.iterdir()})
        self.assertFalse((self.root/'new').exists()); self.assertFalse(list(self.root.glob('.*partial*')))
        write_comparison(r,self.root/'tables',tables_only=True,report_settings=ReportSettings(max_payload_bytes=1))

    def test_unsafe_text_is_data_not_executable_and_ids_are_exact(self):
        r=profiled_result(); l=profile_layer()
        evil='</script><script>globalThis.pwned=1</script><img src=x onerror=alert(1)>\u2028\u2029'
        l['features'][0]['label']=evil
        r=profiled_result(l)
        html,p,_=render_report(r,ReportSettings(max_interactive_depth=1))
        self.assertNotIn(evil,html); self.assertIn('\\u003c/script\\u003e',html)
        embedded=html.split('<script id="comparison-data" type="application/json">')[1].split('</script>')[0]
        self.assertEqual(json.loads(embedded),p)
        exact=['=SUM(A1:A2)','+1','@cmd','-2','001',' Ω\n" ']
        self.assertEqual(json.loads(safe_json(exact)),exact)
        js=asset_text('dashboard.js')
        for unsafe in ('innerHTML','outerHTML','eval(','fetch(','XMLHttpRequest','localStorage','document.write'):
            self.assertNotIn(unsafe,js)
        self.assertIn("connect-src 'none'",html)

    def test_metadata_omission_is_explicit_html_only(self):
        r=profiled_result(); p=build_report_payload(r,ReportSettings(omit_metadata=True,max_interactive_depth=1))
        self.assertEqual(p['layers'],[]); self.assertTrue(p['omissions'])
        self.assertNotIn('observation_ids',p['dataset'])
        self.assertEqual(p['summaries']['outputs'][0]['configuration'],'omitted from HTML')
        out=write_comparison(r,self.root/'out',report_settings=ReportSettings(omit_metadata=True,max_interactive_depth=1))
        self.assertIsNotNone(load_comparison_bundle(out).profiles)

    def test_report_settings_validation_and_unknown_ids(self):
        for args in ({'max_payload_bytes':0},{'max_interactive_depth':True},{'query_ids':['M01','M01']},{'omit_metadata':'yes'}):
            with self.assertRaises(ComparisonValidationError): ReportSettings(**args)
        for args in ({'query_ids':['unknown']},{'pinned_candidate_ids':['unknown']}):
            with self.assertRaises(ComparisonValidationError): build_report_payload(fixture_result(),ReportSettings(**args))
        with self.assertRaises(ComparisonValidationError): ReportSettings.from_dict({'unknown':1})

    def test_backward_compatible_a2_version_one_loader(self):
        r=fixture_result(); out=write_comparison(r,self.root/'old',tables_only=True)
        marker=out/'comparison.json'; m=json.loads(marker.read_text()); m['schema_version']=1; del m['report']; marker.write_text(json.dumps(m))
        self.assertEqual(load_comparison_bundle(out).comparison_id,r.comparison_id)

    def test_report_corruption_detected_even_with_refreshed_inventory(self):
        out=write_comparison(fixture_result(),self.root/'out')
        f=out/'report_payload.json'; p=json.loads(f.read_text()); p['comparison_id']='forged'; f.write_text(json.dumps(p))
        marker=out/'comparison.json'; m=json.loads(marker.read_text()); raw=f.read_bytes()
        m['inventory'][f.name]={'sha256':hashlib.sha256(raw).hexdigest(),'size_bytes':len(raw)}; marker.write_text(json.dumps(m))
        with self.assertRaisesRegex(ComparisonValidationError,'report differs'):
            load_comparison_bundle(out)

    def test_cli_html_tables_and_regeneration(self):
        env={**os.environ,'PYTHONPATH':str(Path('src').resolve())}
        def run(args):
            p=subprocess.run([sys.executable,'-m','valpas.cli','compare',*args],env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
        out=self.root/'out'
        run(['--manifest',str(FIXTURE/'manifest.json'),'--outdir',str(out),'--report-query','M01','--pin-candidate','P03','--max-interactive-depth','2'])
        self.assertTrue((out/'report.html').is_file())
        run(['--bundle',str(out),'--outdir',str(self.root/'again')])
        self.assertEqual((out/'report.html').read_bytes(),(self.root/'again'/'report.html').read_bytes())
        run(['--bundle',str(out),'--outdir',str(self.root/'tables'),'--tables-only'])
        self.assertFalse((self.root/'tables'/'report.html').exists())

    def test_resources_outside_workspace_from_copied_package(self):
        package=self.root/'installed'; shutil.copytree(Path('src/valpas'),package/'valpas')
        env={**os.environ,'PYTHONPATH':str(package)}
        p=subprocess.run([sys.executable,'-c',"from valpas.comparison.browser import asset_text; assert 'reportReady' in asset_text('dashboard.js'); assert '<!doctype html>' in asset_text('shell.html')"],cwd=self.root,env=env,capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr)


class AdditionalScopeCase(unittest.TestCase):
    def test_same_namespace_profiles_and_html(self):
        from test_a1_contracts import descriptor
        from valpas.comparison import load_comparison_input
        outputs=[]
        for oid in ('a','b'):
            d=descriptor(oid)
            d['identity']['candidate_namespace']=copy.deepcopy(d['identity']['query_namespace'])
            outputs.append(load_comparison_input(d))
        r=compare_results(outputs,ComparisonSettings(depths=(1,)))
        layer=profile_layer(r)
        n=len(layer['observation_ids'])
        for f in layer['features']:
            f['values']=[float(i) for i in range(n)]; f['observed']=[True]*n
        r=compare_results(outputs,r.settings,profiles=ProfileData([layer]))
        html,p,_=render_report(r,ReportSettings(max_interactive_depth=1))
        self.assertEqual(p['dataset']['query_namespace'],p['dataset']['candidate_namespace'])
        self.assertIn('Jointly observed',html)
        self.assertTrue(p['details']['q']['profiles'])

    def test_profile_fixture_and_report_settings_are_validated(self):
        r=compare_results(load_manifest(FIXTURE/'manifest-with-profiles.json'))
        self.assertEqual(r.report_settings.max_interactive_depth,5)
        self.assertIsNotNone(r.profiles)
        self.assertEqual(r.comparison_id,fixture_result().comparison_id)


if __name__=='__main__': unittest.main()
