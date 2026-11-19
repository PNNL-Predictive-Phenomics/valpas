"""Portable user state: strict contracts, scope, integrity and bundle durability."""
from copy import deepcopy
from dataclasses import replace, FrozenInstanceError
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from test_a3_report import fixture_result, profiled_result, profile_layer
from test_b1_persistence import b1_result, legacy_bundle, digest_record
from test_b2_reference import fixture_result as reference_result
from valpas.comparison import (Session, Shortlist, load_session, load_shortlist, session_content_id,
    ReportSettings, ComparisonValidationError, write_comparison, load_comparison_bundle, ReferenceData)
from valpas.comparison.browser import render_report, build_report_payload, safe_json
from valpas.comparison.engine import canonical_json


def seal(doc):
    doc=deepcopy(doc);doc.pop('integrity_sha256',None)
    doc['integrity_sha256']=hashlib.sha256(canonical_json(doc).encode()).hexdigest()
    return doc


def chosen(result=None, settings=None):
    s=Session.create(result or b1_result(),settings)
    v=s.to_dict()['view'];v.update(query='M01',candidate='P01',depth=1)
    if v['layers']:
        v['layers'][0].update(color='condition',group='condition',h=1,omission=True,order='metadata',include_fraction=False)
    return s.with_view(v,notes='</script><script>globalThis.pwned=true</script> Ω\u2028')


class SessionCase(unittest.TestCase):
    def test_immutable_detached_roundtrip_and_explicit_user_decisions(self):
        r=b1_result();s=chosen(r)
        s=s.add_decision(decision_id='001',decision='investigate',rationale='Inspect signed scores',timestamp='2026-11-19T00:01:02Z')
        s=s.add_decision(decision_id='002',decision='retain_alternative',rationale='Alternative retained',timestamp='2026-11-19T00:02:02.123456Z')
        s=s.add_decision(decision_id='003',decision='abstain',rationale='No defensible candidate',timestamp='2026-11-19T00:03:02Z')
        self.assertIsNone(s.to_dict()['decisions'][-1]['candidate_id'])
        self.assertEqual(s.to_dict()['decisions'][0]['view']['layers'][0]['h'],1)
        s.validate(r);d=s.to_dict();d['view']['pins'].append('changed')
        self.assertNotEqual(d,s.to_dict())
        with self.assertRaises(FrozenInstanceError):s.document={}
        with tempfile.TemporaryDirectory() as tmp:
            p=s.write(Path(tmp)/'session.json');short=s.shortlist();q=short.write(Path(tmp)/'short.json')
            self.assertEqual(load_session(p,result=r),s)
            self.assertEqual(load_shortlist(q,result=r),short)
            self.assertEqual(load_session(p,result=r),load_session(p,result=r))
            with self.assertRaises(FileExistsError):s.write(p)
        self.assertNotIn('</script>',s.to_json());self.assertIn('\\u003c/script',s.to_json())
        self.assertEqual(json.loads(s.to_json()),s.to_dict())

    def test_unknown_nested_types_ids_and_timestamp_rejected_even_rehashed(self):
        s=chosen().add_decision(decision_id='1',decision='investigate',rationale='because',timestamp='2026-11-19T12:00:00Z')
        mutations=[lambda d:d.update(extra=1),lambda d:d['scope'].update(extra=1),
            lambda d:d['scope']['candidates'][0].update(extra=1),lambda d:d['view'].update(extra=1),
            lambda d:d['view']['layers'][0].update(extra=1),lambda d:d['decisions'][0].update(extra=1),
            lambda d:d['decisions'][0]['view'].update(extra=1),lambda d:d.update(schema_version=True),
            lambda d:d['view'].update(query='unknown'),lambda d:d['view'].update(candidate='unknown'),
            lambda d:d['view'].update(hidden=['unknown']),lambda d:d['view'].update(pins=['unknown']),
            lambda d:d['view'].update(pair=['x','x']),lambda d:d['view'].update(depth=True),
            lambda d:d['view']['layers'][0].update(group='age'),lambda d:d['view']['layers'][0].update(h=0),
            lambda d:d['view']['layers'][0].update(omission=1),lambda d:d['decisions'][0].update(depth=True),
            lambda d:d['view']['layers'][0].update(h=9007199254740992),
            lambda d:d['scope'].update(max_depth=9007199254740992),
            lambda d:d['decisions'][0].update(rationale=' \n '),lambda d:d['decisions'][0].update(inspected_output_ids=[]),
            lambda d:d['decisions'].append(deepcopy(d['decisions'][0])),
            lambda d:d['decisions'][0].update(decision='model_correct'),
            lambda d:d['decisions'][0].update(decision='abstain')]
        for mutate in mutations:
            d=s.to_dict();mutate(d)
            with self.subTest(mutate=mutate),self.assertRaises(ComparisonValidationError):Session.from_dict(seal(d))
        for timestamp in ('','now','2026-11-19','2026-11-19T12:00:00','2026-02-30T12:00:00Z',
                          '2026-11-19T24:00:00Z','1960-01-01T00:00:00Z',True):
            d=s.to_dict();d['decisions'][0]['timestamp']=timestamp
            with self.subTest(timestamp=timestamp),self.assertRaises(ComparisonValidationError):Session.from_dict(seal(d))

    def test_tamper_comparison_content_and_reference_binding(self):
        r=b1_result();s=chosen(r);d=s.to_dict();d['notes']='tampered'
        with self.assertRaisesRegex(ComparisonValidationError,'checksum'):Session.from_dict(d)
        d=s.to_dict();d['comparison_id']='wrong';wrong=Session.from_dict(seal(d))
        with self.assertRaisesRegex(ComparisonValidationError,'comparison ID'):wrong.validate(r)
        layer=profile_layer();layer['features'][0]['values'][0]=42
        other=profiled_result(layer)
        self.assertEqual(other.comparison_id,r.comparison_id)
        with self.assertRaisesRegex(ComparisonValidationError,'content binding'):s.validate(other)
        changed=replace(r,sample_metadata=replace(r.sample_metadata,records=()))
        with self.assertRaisesRegex(ComparisonValidationError,'content binding'):s.validate(changed)
        refs=reference_result();s=Session.create(refs);raw=refs.references.to_dict();raw['endpoints'][0]['description']='new provenance'
        changed=replace(refs,references=ReferenceData.from_dict(raw))
        self.assertEqual(changed.comparison_id,refs.comparison_id)
        with self.assertRaisesRegex(ComparisonValidationError,'content binding'):s.validate(changed)

    def test_explicit_scope_rebind_never_silently_clamps_or_loses_decisions(self):
        r=b1_result();small=ReportSettings(query_ids=('M01',),max_interactive_depth=1)
        s=chosen(r,small).add_decision(decision_id='a',decision='abstain',rationale='uncertain',timestamp='2026-11-19T00:00:00Z')
        broad=ReportSettings(max_interactive_depth=3)
        with self.assertRaisesRegex(ComparisonValidationError,'scope changed'):s.validate(r,broad)
        expanded=s.rebind_scope(r,broad);expanded.validate(r,broad)
        self.assertEqual(expanded.to_dict()['decisions'],s.to_dict()['decisions'])
        self.assertEqual(expanded.to_dict()['content_id'],s.to_dict()['content_id'])
        with self.assertRaises(ComparisonValidationError):expanded.rebind_scope(r,replace(small,query_ids=('M02',)))
        deep=expanded.to_dict()['view'];deep['depth']=3
        with self.assertRaises(ComparisonValidationError):expanded.with_view(deep).rebind_scope(r,small)
        with self.assertRaises(ComparisonValidationError):expanded.rebind_scope(r,replace(broad,omit_metadata=True))

    def test_initial_session_bundle_source_free_budget_and_omission(self):
        r=b1_result();settings=ReportSettings(max_interactive_depth=2);s=chosen(r,settings)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=write_comparison(r,root/'out',report_settings=settings,initial_session=s)
            loaded=load_comparison_bundle(out);self.assertEqual(loaded.initial_session,s)
            again=write_comparison(loaded,root/'again')
            self.assertEqual((out/'report.html').read_bytes(),(again/'report.html').read_bytes())
            self.assertEqual(loaded.comparison_id,r.comparison_id)
            m=json.loads((out/'comparison.json').read_text());self.assertEqual(m['b2_session'],{'schema_version':1})
            baseline=render_report(r,settings)[2]['payload_bytes']
            with self.assertRaisesRegex(ComparisonValidationError,'before HTML wrapping'):
                write_comparison(r,root/'large',report_settings=replace(settings,max_payload_bytes=baseline),initial_session=s)
            self.assertFalse((root/'large').exists())
            private=replace(settings,omit_metadata=True);blank=Session.create(r,private)
            with self.assertRaisesRegex(ComparisonValidationError,'does not redact user notes'):
                render_report(replace(r,initial_session=blank),private)
            out2=write_comparison(r,root/'tables',tables_only=True,report_settings=private,initial_session=blank)
            self.assertEqual(load_comparison_bundle(out2).initial_session,blank)
            p=out/'initial_session.json';d=json.loads(p.read_text());d['notes']='tamper';p.write_text(json.dumps(d))
            m['inventory'][p.name]=digest_record(p);(out/'comparison.json').write_text(json.dumps(m))
            with self.assertRaisesRegex(ComparisonValidationError,'checksum'):load_comparison_bundle(out)

    def test_old_reference_assets_and_payload_without_session_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=reference_result();out=write_comparison(r,Path(tmp)/'old')
            p=out/'report_payload.json';old=p.read_text();d=json.loads(old)
            for name in ('session_content_id','session_contract','initial_session'):d.pop(name)
            raw=safe_json(d);p.write_text(raw)
            h=out/'report.html';h.write_text(h.read_text().replace(old,raw).replace('7 · User decisions, sessions and shortlists','Old renderer'))
            m=json.loads((out/'comparison.json').read_text())
            for file in (p,h):m['inventory'][file.name]=digest_record(file)
            m['report']['payload']={'payload_bytes':len(raw.encode()),'payload_sha256':hashlib.sha256(raw.encode()).hexdigest()}
            (out/'comparison.json').write_text(json.dumps(m))
            self.assertEqual(load_comparison_bundle(out).reference_provenance_hash,r.reference_provenance_hash)

    def test_canonical_ids_formula_safe_csv_and_duplicate_json_keys(self):
        from test_a1_contracts import descriptor
        from valpas.comparison import load_comparison_input, compare_results
        outputs=[];q='001';c=' \t=SUM(A1:A2)</script> Ω'
        for oid in ('a','b'):
            d=descriptor(oid);d['query_ids']=[q];d['candidate_ids']=[c]
            d['data']['inline']={'row_ids':[q],'column_ids':[c],'values':[[1]]}
            outputs.append(load_comparison_input(d))
        r=compare_results(outputs);s=Session.create(r);v=s.to_dict()['view'];v.update(query=q,candidate=c)
        s=s.with_view(v).add_decision(decision_id='0001',decision='investigate',rationale='@cmd\ntext',timestamp='2026-11-19T12:00:00Z')
        short=s.shortlist();self.assertEqual(json.loads(short.to_json())['decisions'][0]['candidate_id'],c)
        import csv,io
        rows=list(csv.reader(io.StringIO(short.to_csv())))
        self.assertTrue(all(cell.startswith("'") for cell in rows[1]));self.assertEqual(rows[1][3],"'"+c)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'duplicate.json';p.write_text(s.to_json().replace('"notes":','"notes":"x","notes":'))
            with self.assertRaises(ComparisonValidationError):load_session(p)


if __name__=='__main__':unittest.main()
