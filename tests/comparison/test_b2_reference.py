"""B2 evidence mathematics, strict contracts and fixed-engine invariants."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from test_a1_contracts import descriptor, prefix_descriptor, table_descriptor
from valpas.comparison import (ComparisonSettings, ComparisonValidationError, ReferenceData,
    QueryGroups, compare_results, load_manifest, load_comparison_input, load_reference_data,
    load_query_groups, reference_provenance_hash)
from valpas.comparison.engine import TABLE_COLUMNS
from valpas.comparison.models import thaw

FIXTURE = Path(__file__).parent / 'fixtures' / 'b2-reference'


def fixture_result(weighting='feature'):
    manifest = load_manifest(FIXTURE / 'manifest.json')
    return compare_results(manifest, references=replace(manifest.references, weighting=weighting))


def simple_refs(outputs, **changes):
    data = dict(schema_version=1, dataset=thaw(outputs[0].descriptor['identity']), endpoints=[{
        'endpoint_id':'direct', 'source':'local', 'version':'1', 'evidence_type':'reaction',
        'support_class':'direct', 'assessed_query_ids':['q'], 'candidate_universe':['a','b','c','outside']}],
        evidence=[{'endpoint_id':'direct','query_id':'q','candidate_id':'b','evidence_id':'r1'}])
    data.update(changes)
    return ReferenceData.from_dict(data)


def summary(result, **filters):
    scope = dict(endpoint_id='direct', output_id='A', requested_depth=1, cohort='all_assessed',
                 opportunity_stratum='all', metric='hit') | filters
    return next(r for r in result.iter_table('reference_summary') if all(r[k] == v for k,v in scope.items()))


def recovery(result, **filters):
    scope = dict(endpoint_id='direct', output_id='A', requested_depth=1, query_id='q1') | filters
    return next(r for r in result.iter_table('reference_recovery') if all(r[k] == v for k,v in scope.items()))


class ReferenceContractsCase(unittest.TestCase):
    def setUp(self):
        self.raw = json.loads((FIXTURE / 'references.json').read_text())
        self.groups = json.loads((FIXTURE / 'query-groups.json').read_text())

    def test_detached_exact_ids_and_duplicate_normalization(self):
        refs = ReferenceData.from_dict(self.raw)
        self.assertEqual(len(refs.evidence), len(self.raw['evidence'])-1)
        before = refs.to_dict()
        self.raw['evidence'][0]['candidate_id'] = 'changed'
        self.assertEqual(refs.to_dict(), before)
        with self.assertRaises(TypeError): refs.evidence[0]['query_id'] = 'changed'
        with self.assertRaises(TypeError): refs.endpoints[0]['source'] = 'changed'

    def test_schema_unknown_nested_keys_and_versions(self):
        mutations = [lambda d:d.update(schema_version=True), lambda d:d.update(schema_version=2),
            lambda d:d.update(weigthing='group'), lambda d:d['endpoints'][0].update(suport_class='direct'),
            lambda d:d['evidence'][0].update(evidence_typ='reaction'),
            lambda d:d['dataset']['query_namespace'].update(modailty='protein'),
            lambda d:d.update(weighting='best_peak'), lambda d:d.update(endpoints=[]),
            lambda d:d.update(evidence={}), lambda d:d['endpoints'][0].update(assessed_query_ids=None)]
        for mutate in mutations:
            d=copy.deepcopy(self.raw); mutate(d)
            with self.subTest(mutate=mutate), self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)

    def test_endpoint_separation_and_invalid_unions(self):
        for change in [dict(evidence_type='pathway', support_class='direct'), dict(evidence_type='union'),
                       dict(support_class='direct+inferred')]:
            d=copy.deepcopy(self.raw); d['endpoints'][0].update(change)
            with self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)
        for field in ['endpoint_id','source','version']:
            d=copy.deepcopy(self.raw); d['endpoints'][0][field]=None
            with self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)
        d=copy.deepcopy(self.raw); d['endpoints'].append(copy.deepcopy(d['endpoints'][0]))
        with self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)
        d['endpoints'][-1]['endpoint_id']='renamed'
        with self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)

    def test_explicit_coverage_universe_and_exact_identifiers(self):
        mutations = [lambda d:d['evidence'][0].update(query_id='qN'),
            lambda d:d['evidence'][0].update(candidate_id='unknown'),
            lambda d:d['evidence'][0].update(endpoint_id='unknown'),
            lambda d:d['evidence'][0].update(evidence_id=1),
            lambda d:d['endpoints'][0]['candidate_universe'].append('a'),
            lambda d:d['endpoints'][0]['assessed_query_ids'].append('q1')]
        for mutate in mutations:
            d=copy.deepcopy(self.raw); mutate(d)
            with self.assertRaises(ComparisonValidationError): ReferenceData.from_dict(d)
        d=copy.deepcopy(self.raw); d['endpoints'][0]['candidate_universe'].append(' a ')
        d['evidence'][0]['candidate_id']=' a '
        self.assertIn(' a ', ReferenceData.from_dict(d).endpoints[0]['candidate_universe'])

    def test_binding_rejects_mismatches_unknown_queries(self):
        manifest=load_manifest(FIXTURE/'manifest.json')
        for key,value in [('dataset_id','other'),('context','other'),('observation_ids',['other']),
                          ('query_namespace',{'id':'other','modality':'protein'}),
                          ('dataset_evidence',None)]:
            d=copy.deepcopy(self.raw); d['dataset'][key]=value
            with self.assertRaises(ComparisonValidationError): compare_results(manifest, references=ReferenceData.from_dict(d))
        d=copy.deepcopy(self.raw); d['endpoints'][0]['assessed_query_ids'].append('outside-query')
        with self.assertRaises(ComparisonValidationError): compare_results(manifest, references=ReferenceData.from_dict(d))
        d=copy.deepcopy(self.raw); d['dataset']['observation_ids'].reverse()
        self.assertEqual(compare_results(manifest, references=ReferenceData.from_dict(d)).comparison_id,
                         compare_results(manifest).comparison_id)

    def test_groups_reject_ambiguous_duplicate_unbound_and_unknown_membership(self):
        for group in ('G1','another'):
            d=copy.deepcopy(self.groups); d['records'].append(dict(query_id='q1',group_id=group))
            with self.assertRaises(ComparisonValidationError): QueryGroups.from_dict(d)
        for field,value in [('schema_version',True),('typo',1)]:
            d=copy.deepcopy(self.groups); d[field]=value
            with self.assertRaises(ComparisonValidationError): QueryGroups.from_dict(d)
        m=load_manifest(FIXTURE/'manifest.json')
        for mutate in [lambda d:d['dataset'].update(dataset_id='other'),lambda d:d['records'][0].update(query_id='unknown')]:
            d=copy.deepcopy(self.groups); mutate(d)
            with self.assertRaises(ComparisonValidationError): compare_results(m,query_groups=QueryGroups.from_dict(d))
        with self.assertRaises(ComparisonValidationError):
            compare_results(m.outputs,references=replace(m.references,weighting='group'))
        with self.assertRaises(ComparisonValidationError): compare_results(m.outputs,query_groups=m.query_groups)

    def test_local_loaders_hash_bytes_reject_unsafe_paths(self):
        for loader,name in [(load_reference_data,'references.json'),(load_query_groups,'query-groups.json')]:
            obj=loader({'path':name},base_dir=FIXTURE)
            self.assertEqual(obj.source_fingerprints[0]['sha256'], hashlib.sha256((FIXTURE/name).read_bytes()).hexdigest())
            self.assertEqual(obj.source_fingerprints[0]['size_bytes'],len((FIXTURE/name).read_bytes()))
            for path in ['../'+name,'https://example.test/'+name,'/'+name]:
                with self.assertRaises(ComparisonValidationError): loader({'path':path},base_dir=FIXTURE)
            with self.assertRaises(ComparisonValidationError): loader({'path':name,'allow_network':True},base_dir=FIXTURE)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.json'; p.write_text('{"schema_version":1,"schema_version":1}')
            with self.assertRaises(ComparisonValidationError):load_reference_data({'path':p.name},base_dir=tmp)
            p=Path(tmp)/'bad.pkl'; p.write_text('{}')
            with self.assertRaises(ComparisonValidationError):load_reference_data({'path':p.name},base_dir=tmp)


class ReferenceMathCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.result=fixture_result()

    def test_known_fixture_math_and_statuses(self):
        expected={'q0':(0,0,0,None,None,'assessed_zero','0'),
                  'q1':(1,1,1,1,1,'available','1'),
                  'q2':(3,2,1,.5,2/3,'available','2-5'),
                  'q6':(6,6,1,1/6,1,'available','6+'),
                  'qU':(1,0,0,None,0,'unreachable','0'),
                  'qN':(None,None,None,None,None,'unassessed',None)}
        for q, values in expected.items():
            row=recovery(self.result,query_id=q)
            self.assertEqual(tuple(row[k] for k in ['total_known_support','reachable_support','hit','recovery','reachability_fraction','status','opportunity_stratum']), values)
        row=recovery(self.result,query_id='q2',requested_depth=2)
        self.assertEqual((row['nomination_list_size'],row['supported_nominations'],row['reference_supported_fraction'],row['recovery']), (2,2,1,1))
        row=recovery(self.result,requested_depth=10)
        self.assertEqual((row['nomination_list_size'],row['reference_supported_fraction']), (6,1/6))

    def test_sources_versions_direct_inferred_pathway_independent(self):
        for endpoint in ['direct','inferred','pathway','other-source','other-version']:
            row=recovery(self.result,endpoint_id=endpoint)
            self.assertEqual(row['total_known_support'],1)
            self.assertEqual(row['hit'],int(endpoint=='direct'))
        self.assertEqual(recovery(self.result,output_id='B',endpoint_id='inferred')['hit'],1)
        self.assertEqual(recovery(self.result,output_id='B')['hit'],0)

    def test_all_assessed_reachable_and_metric_denominators(self):
        all_row=summary(self.result); reachable=summary(self.result,cohort='reachable')
        self.assertEqual((all_row['declared_queries'],all_row['assessed_queries'],all_row['evaluable_queries'],all_row['mean']), (6,5,5,3/5))
        self.assertEqual((reachable['evaluable_queries'],reachable['mean']), (3,1))
        rec=summary(self.result,metric='recovery')
        self.assertEqual(rec['aggregation_denominator'],3)
        self.assertAlmostEqual(rec['mean'],5/9)
        self.assertEqual(rec['exclusion_reasons'],{'no_reachable_support':2,'query_unassessed':1})
        reach=summary(self.result,metric='reachability_fraction')
        self.assertEqual(reach['aggregation_denominator'],4)
        self.assertAlmostEqual(reach['mean'],2/3)
        self.assertEqual(summary(self.result,output_id='B')['mean'],2/5)

    def test_equal_group_means_not_best_feature_or_pooled_features(self):
        result=fixture_result('group')
        row=summary(result)
        self.assertAlmostEqual(row['mean'],5/9)  # ((0+1+1)/3 + 1 + 0)/3
        self.assertEqual(row['aggregation_denominator'],3)
        self.assertEqual(row['evaluable_queries'],5)
        self.assertEqual([(g['group_size'],g['evaluable_features']) for g in row['groups']],[(3,3),(1,1),(2,1)])
        row=summary(result,metric='recovery')
        self.assertAlmostEqual(row['mean'],11/24)  # ((1+.5)/2 + 1/6)/2
        self.assertEqual(row['evaluable_groups'],2)
        self.assertEqual(row['groups'][2]['mean'],None)

    def test_missing_groups_exclusions_and_feature_default(self):
        r=self.result
        groups=replace(r.query_groups,records=[g for g in r.query_groups.records if g['query_id']!='q6'])
        feature=replace(r,query_groups=groups)
        self.assertEqual(summary(feature)['mean'],3/5)
        group=replace(feature,references=replace(r.references,weighting='group'))
        row=summary(group)
        self.assertEqual(row['feature_exclusions']['q6'],'missing_query_group')
        self.assertEqual((row['evaluable_queries'],row['aggregation_denominator']),(4,2))
        self.assertAlmostEqual(row['mean'],1/3)

    def test_strata_including_empty_and_zero_opportunity(self):
        for stratum,count,mean in [('0',2,0),('1',1,1),('2-5',1,1),('6+',1,1)]:
            row=summary(self.result,opportunity_stratum=stratum)
            self.assertEqual((row['evaluable_queries'],row['mean']),(count,mean))
            self.assertEqual(row['stratum_edges'],[['0',0,0],['1',1,1],['2-5',2,5],['6+',6,None]])
        row=summary(self.result,cohort='reachable',opportunity_stratum='0')
        self.assertEqual((row['aggregation_denominator'],row['mean'],row['status']),(0,None,'unavailable'))

    def test_reference_changes_never_change_engine_tables_or_comparison_id(self):
        m=load_manifest(FIXTURE/'manifest.json'); baseline=compare_results(m.outputs,m.settings)
        changed=replace(m.references,evidence=[])
        for result in [self.result,compare_results(m,references=changed),fixture_result('group')]:
            self.assertEqual(result.comparison_id,baseline.comparison_id)
            for table in TABLE_COLUMNS:
                self.assertEqual(list(result.iter_table(table)),list(baseline.iter_table(table)),table)
        self.assertNotEqual(self.result.reference_provenance_hash,compare_results(m,references=changed).reference_provenance_hash)

    def test_normalized_provenance_order_duplicates_paths_and_weighting(self):
        refs=self.result.references; raw=refs.to_dict()
        raw['endpoints'].reverse(); raw['evidence'].reverse(); raw['evidence'].append(raw['evidence'][0])
        for e in raw['endpoints']:e['candidate_universe'].reverse();e['assessed_query_ids'].reverse()
        raw['dataset']['observation_ids'].reverse()
        a=reference_provenance_hash(refs,self.result.query_groups)
        b=reference_provenance_hash(ReferenceData.from_dict(raw),self.result.query_groups)
        self.assertEqual(a,b)
        self.assertNotEqual(a,reference_provenance_hash(replace(refs,weighting='group'),self.result.query_groups))

    def test_strict_gap_common_native_and_empty_pool(self):
        outputs=[load_comparison_input(descriptor('A',[3,None,1])),load_comparison_input(descriptor('B',[3,2,1]))]
        refs=simple_refs(outputs)
        for policy in ['strict','common','native_inspection']:
            r=compare_results(outputs,ComparisonSettings(pool_policy=policy,depths=(1,)),references=refs)
            row=recovery(r,query_id='q')
            if policy=='strict':self.assertEqual((row['status'],row['hit']),('unavailable',None))
            else:self.assertEqual((row['status'],row['hit'],row['recovery']),('unreachable',0,None))
            self.assertEqual(row['reachable_support'],0)
        outputs=[load_comparison_input(descriptor(o,[None,None,None])) for o in ['A','B']]
        r=compare_results(outputs,ComparisonSettings(depths=(1,)),references=simple_refs(outputs))
        row=recovery(r,query_id='q'); self.assertEqual((row['status'],row['hit'],row['nomination_list_size']),('unavailable',None,0))

    def test_prefix_depth_and_unknown_reachability_never_fabricated(self):
        outputs=[load_comparison_input(prefix_descriptor(o)) for o in ['A','B']]
        r=compare_results(outputs,ComparisonSettings(depths=(1,3)),references=simple_refs(outputs))
        row=recovery(r,query_id='q')
        self.assertEqual((row['hit'],row['reference_supported_fraction'],row['reachable_support'],row['recovery'],row['status']), (1,1,None,None,'limited_depth'))
        deep=recovery(r,query_id='q',requested_depth=3)
        self.assertEqual((deep['hit'],deep['reason'],deep['status']),(None,'insufficient_certified_depth','limited_depth'))
        outputs=[load_comparison_input(prefix_descriptor(o,3)) for o in ['A','B']]
        row=recovery(compare_results(outputs,ComparisonSettings(depths=(10,)),references=simple_refs(outputs)),query_id='q',requested_depth=10)
        self.assertEqual((row['reachable_support'],row['recovery'],row['nomination_list_size']),(1,1,3))

    def test_filtered_lists_are_unavailable_not_zero(self):
        ds=[table_descriptor('filtered_list',o) for o in ['A','B']]
        for d in ds:d['completeness']={'kind':'inspection_only','filter':'saved subset'};d['missing_policy']['absent']='unreported'
        outputs=[load_comparison_input(d) for d in ds]
        row=recovery(compare_results(outputs,ComparisonSettings(depths=(1,)),references=simple_refs(outputs)),query_id='q')
        self.assertEqual((row['status'],row['hit'],row['recovery']),('unavailable',None,None))

    def test_common_excluded_queries_remain_in_reference_denominators(self):
        m=load_manifest(FIXTURE/'manifest.json'); d=thaw(m.outputs[1].descriptor)
        d['query_ids'].remove('q1'); d['data']={'format':'json','inline':{'row_ids':d['query_ids'],'column_ids':list('abcdef'),'values':[[6,5,4,3,2,1] for q in d['query_ids']]}}
        outputs=[m.outputs[0],load_comparison_input(d)]
        r=compare_results(outputs,ComparisonSettings(pool_policy='common',depths=(1,)),references=m.references)
        self.assertEqual(recovery(r)['reason'],'query_not_shared_by_all_outputs')
        self.assertEqual(summary(r)['assessed_queries'],5)
        self.assertEqual(summary(r)['evaluable_queries'],4)

    def test_same_namespace_self_exclusion_consumes_engine_pool(self):
        ds=[descriptor(o) for o in ['A','B']]
        for d in ds:
            d['identity']['candidate_namespace']=copy.deepcopy(d['identity']['query_namespace'])
            d['candidate_ids']=['q','b','c'];d['data']['inline']['column_ids']=['q','b','c']
        outputs=[load_comparison_input(d) for d in ds]
        raw=simple_refs(outputs).to_dict();raw['endpoints'][0]['candidate_universe']=['q','b','c'];raw['evidence'][0]['candidate_id']='q'
        r=compare_results(outputs,ComparisonSettings(depths=(1,)),references=ReferenceData.from_dict(raw))
        row=recovery(r,query_id='q');self.assertEqual((row['total_known_support'],row['reachable_support'],row['status']),(1,0,'unreachable'))


if __name__ == '__main__': unittest.main()
