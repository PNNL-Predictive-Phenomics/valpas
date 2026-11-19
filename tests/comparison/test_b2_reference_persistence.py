"""Reference extension integrity, bounded HTML and source-free CLI/API reload."""
from dataclasses import replace
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_b2_reference import FIXTURE, fixture_result
from test_b1_persistence import legacy_bundle
from test_a3_report import fixture_result as baseline_result
from valpas.comparison import (ReferenceData, ReportSettings, ComparisonValidationError,
    compare_results, load_manifest, load_comparison_bundle, write_comparison)
from valpas.comparison.browser import build_report_payload, render_report, safe_json
from valpas.comparison.engine import TABLE_COLUMNS
from valpas.comparison.models import thaw


class ReferencePersistenceCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def marker(self, path): return json.loads((path/'comparison.json').read_text())

    def edit(self,path,mutate):
        m=self.marker(path);mutate(m);(path/'comparison.json').write_text(json.dumps(m))

    def refresh(self,path,name):
        raw=(path/name).read_bytes()
        self.edit(path,lambda m:m['inventory'].update({name:{'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}))

    def assert_tables(self,a,b):
        self.assertEqual(a.table_columns,b.table_columns)
        self.assertEqual(a.comparison_id,b.comparison_id)
        self.assertEqual(a.reference_provenance_hash,b.reference_provenance_hash)
        for table in a.table_names:self.assertEqual(list(a.iter_table(table)),list(b.iter_table(table)),table)

    def test_roundtrip_optional_exact_tables_normalized_refs_groups(self):
        result=fixture_result('group')
        out=write_comparison(result,self.root/'out')
        m=self.marker(out)
        self.assertEqual(m['schema_version'],3)
        self.assertEqual(m['b2_references'],{'schema_version':1,'query_groups':True,'provenance_hash':result.reference_provenance_hash})
        self.assertEqual(set(m['tables']),set(TABLE_COLUMNS)|{'reference_endpoints','reference_evidence','reference_recovery','reference_summary','query_groups'})
        self.assertEqual(json.loads((out/'references.json').read_text()),result.references.to_dict())
        self.assertEqual(json.loads((out/'query_groups.json').read_text()),result.query_groups.to_dict())
        self.assert_tables(result,load_comparison_bundle(out))
        with (out/'reference_recovery.csv').open(newline='') as handle:
            rows=list(csv.reader(handle))
        self.assertEqual(len(rows)-1,len(list(result.iter_table('reference_recovery'))))
        self.assertIn('metric_reasons',rows[0])
        self.assertIn('not biological negatives',m['table_schema']['reference_recovery']['units'])

    def test_absent_references_and_optional_groups_preserve_table_contract(self):
        m=load_manifest(FIXTURE/'manifest.json')
        baseline=compare_results(m.outputs,m.settings)
        out=write_comparison(baseline,self.root/'none',tables_only=True)
        self.assertNotIn('b2_references',self.marker(out))
        self.assertEqual(set(baseline.table_names),set(TABLE_COLUMNS))
        result=compare_results(m.outputs,m.settings,references=m.references)
        out=write_comparison(result,self.root/'refs',tables_only=True)
        self.assertNotIn('query_groups',self.marker(out)['tables'])
        self.assert_tables(result,load_comparison_bundle(out))

    def test_consumed_source_hashes_protection_deleted_sources_regeneration(self):
        source=self.root/'source';shutil.copytree(FIXTURE,source)
        result=compare_results(load_manifest(source/'manifest.json'))
        sources={r['role']:r for r in result.source_fingerprints}
        for role,name in [('references','references.json'),('query_groups','query-groups.json')]:
            self.assertEqual(sources[role]['sha256'],hashlib.sha256((source/name).read_bytes()).hexdigest())
        with self.assertRaisesRegex(ComparisonValidationError,'consumed source'):
            write_comparison(result,source,overwrite=True)
        out=write_comparison(result,self.root/'saved')
        shutil.rmtree(source)
        loaded=load_comparison_bundle(out)
        self.assert_tables(result,loaded)
        self.assertEqual(thaw(loaded.source_fingerprints),thaw(result.source_fingerprints))
        again=write_comparison(loaded,self.root/'again')
        self.assert_tables(result,load_comparison_bundle(again))
        with self.assertRaisesRegex(ComparisonValidationError,'consumed source'):
            write_comparison(loaded,out,overwrite=True)

    def test_checksum_and_exact_table_parity_even_after_rehash(self):
        for index,name in enumerate(['references.json','query_groups.json','reference_evidence.csv','reference_recovery.csv','reference_summary.csv','reference_endpoints.csv']):
            out=write_comparison(fixture_result(),self.root/str(index),tables_only=True)
            with (out/name).open('a') as handle:handle.write('corruption')
            with self.assertRaisesRegex(ComparisonValidationError,'checksum'):load_comparison_bundle(out)
        out=write_comparison(fixture_result(),self.root/'parity',tables_only=True)
        p=out/'reference_summary.csv'
        with p.open(newline='') as handle:
            rows=list(csv.reader(handle))
        col=rows[0].index('mean');rows[1][col]='999'
        with p.open('w',newline='') as handle:csv.writer(handle).writerows(rows)
        self.refresh(out,p.name)
        with self.assertRaisesRegex(ComparisonValidationError,'table differs'):load_comparison_bundle(out)

    def test_normalized_provenance_and_extension_inventory_checked(self):
        for index,mutate in enumerate([
            lambda m:m['b2_references'].update(schema_version=True),
            lambda m:m['b2_references'].update(query_groups=False),
            lambda m:m['b2_references'].update(provenance_hash='wrong'),
            lambda m:m['b2_references'].update(typo=1),
            lambda m:m.pop('b2_references'),
            lambda m:m.update(schema_version=2),
            lambda m:m['table_schema']['reference_recovery'].update(columns=['wrong'])]):
            out=write_comparison(fixture_result(),self.root/str(index),tables_only=True)
            self.edit(out,mutate)
            with self.assertRaises(ComparisonValidationError):load_comparison_bundle(out)
        out=write_comparison(fixture_result(),self.root/'normalized',tables_only=True)
        raw=json.loads((out/'references.json').read_text());raw['evidence'][0]['description']='altered'
        (out/'references.json').write_text(json.dumps(raw));self.refresh(out,'references.json')
        with self.assertRaisesRegex(ComparisonValidationError,'provenance hash'):load_comparison_bundle(out)

    def test_full_cohort_summary_detail_bounded_evidence_and_pins(self):
        result=fixture_result()
        settings=ReportSettings(query_ids=('q1',),max_interactive_depth=1)
        payload=build_report_payload(result,settings)
        self.assertEqual(payload['all_query_ids'],['q0','q1','q2','q6','qN','qU'])
        self.assertEqual(set(payload['details']),{'q1'})
        self.assertEqual({r['query_id'] for r in payload['references']['recovery']},set(payload['all_query_ids']))
        self.assertTrue(all(r['query_id']=='q1' and r['candidate_id'] in ['a','b'] for r in payload['references']['evidence']))
        baseline=list(result.iter_table('reference_summary'))
        self.assertEqual(payload['references']['summary'],baseline)
        pinned=build_report_payload(result,replace(settings,pinned_candidate_ids=('c',)))
        self.assertTrue(any(r['endpoint_id']=='pathway' for r in pinned['references']['evidence']))
        self.assertEqual(payload['references']['summary'],pinned['references']['summary'])

    def test_metadata_omission_and_inclusive_payload_budget_atomic_failure(self):
        r=fixture_result();raw=r.references.to_dict();secret='PRIVATE_REFERENCE_DESCRIPTION'
        raw['endpoints'][0]['description']=secret+' </script><script>globalThis.pwned=true</script>'
        r=replace(r,references=ReferenceData.from_dict(raw))
        settings=ReportSettings(max_interactive_depth=1)
        html,payload,record=render_report(r,settings)
        self.assertIn(secret,html)
        self.assertNotIn('</script><script>globalThis.pwned=true</script>',html)
        omitted=build_report_payload(r,replace(settings,omit_metadata=True))
        self.assertIsNone(omitted['references']);self.assertNotIn(secret,safe_json(omitted))
        self.assertIn('all reference endpoints',' '.join(omitted['omissions']))
        baseline=replace(r,references=None,query_groups=None)
        _,_,base_record=render_report(baseline,settings)
        self.assertGreater(record['payload_bytes'],base_record['payload_bytes'])
        out=write_comparison(r,self.root/'out',report_settings=settings)
        before={p.name:p.read_bytes() for p in out.iterdir()}
        with self.assertRaisesRegex(ComparisonValidationError,'before HTML wrapping'):
            write_comparison(r,out,overwrite=True,report_settings=replace(settings,max_payload_bytes=base_record['payload_bytes']))
        self.assertEqual(before,{p.name:p.read_bytes() for p in out.iterdir()})
        self.assertFalse(list(self.root.glob('.*partial*')))
        omitted_out=write_comparison(r,self.root/'omit',report_settings=replace(settings,omit_metadata=True))
        self.assertIn(secret,(omitted_out/'references.json').read_text())
        self.assert_tables(r,load_comparison_bundle(omitted_out))

    def test_same_version_v1_v2_v3_legacy_html_and_tables(self):
        for version in [1,2]:
            out=legacy_bundle(baseline_result(),self.root/str(version),version,html=version==2)
            loaded=load_comparison_bundle(out);self.assertIsNone(loaded.references)
            write_comparison(loaded,self.root/(str(version)+'-again'))
        out=write_comparison(baseline_result(),self.root/'v3')
        # Old v3 assets may differ, but inventory + payload/science parity must hold.
        p=out/'report.html';p.write_text(p.read_text().replace('6 · Source-specific reference evidence','Historical reference-free report'))
        self.refresh(out,p.name)
        loaded=load_comparison_bundle(out);self.assertIsNone(loaded.references)
        self.edit(out,lambda m:m.update(software_version='other-version'))
        with self.assertRaises(ComparisonValidationError):load_comparison_bundle(out)

    def test_cli_reference_manifest_and_deleted_source_bundle(self):
        source=self.root/'source';shutil.copytree(FIXTURE,source)
        out=self.root/'cli';env={**os.environ,'PYTHONPATH':str(Path('src').resolve())}
        for args in [ ['--manifest',str(source/'manifest.json'),'--outdir',str(out)],
                      ['--bundle',str(out),'--outdir',str(self.root/'again'),'--tables-only'] ]:
            p=subprocess.run([sys.executable,'-m','valpas.cli','compare',*args],env=env,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            if source.exists():shutil.rmtree(source)
        self.assert_tables(load_comparison_bundle(out),load_comparison_bundle(self.root/'again'))

    def test_no_heavy_imports_or_training_on_reference_path(self):
        script = '''
import sys, importlib.abc, tempfile
from pathlib import Path
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','numpy','pandas','scipy','matplotlib'} or fullname.startswith('valpas._core'):
            raise AssertionError('heavy/training import '+fullname)
sys.meta_path.insert(0,Block())
from valpas.comparison import load_manifest, compare_results, write_comparison, load_comparison_bundle
r=compare_results(load_manifest(sys.argv[1]))
with tempfile.TemporaryDirectory() as tmp:
    p=write_comparison(r,Path(tmp)/'out')
    again=load_comparison_bundle(p)
    assert again.reference_provenance_hash == r.reference_provenance_hash
    assert list(again.iter_table('reference_summary')) == list(r.iter_table('reference_summary'))
'''
        p=subprocess.run([sys.executable,'-c',script,str(FIXTURE/'manifest.json')],capture_output=True,text=True,
                         env={**os.environ,'PYTHONPATH':str(Path('src').resolve())})
        self.assertEqual(p.returncode,0,p.stderr)


if __name__=='__main__':unittest.main()
