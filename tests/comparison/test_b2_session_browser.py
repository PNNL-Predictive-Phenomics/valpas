"""Actual Chrome Blob downloads and DOM file-input imports, not parser stubs."""
from dataclasses import replace
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

from chrome_cdp import ChromeCDP
from test_a3_browser import CHROME
from test_b1_persistence import b1_result
from test_b2_reference import fixture_result as reference_result
from test_b2_session import seal, chosen
from valpas.comparison import ReportSettings, Session, load_session, load_shortlist
from valpas.comparison.browser import render_report


@unittest.skipUnless(CHROME,'Existing Chrome required for real downloaded-file/import tests')
class SessionBrowserCase(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.chrome=ChromeCDP(CHROME,self.root);self.addCleanup(self.chrome.close)

    def open_report(self,result,settings=None,name='report.html'):
        p=self.root/name;p.write_text(render_report(result,settings)[0]);self.chrome.open(p);return p

    def click(self,selector):
        self.chrome.evaluate('document.querySelector('+json.dumps(selector)+').click()')

    def status(self):return self.chrome.evaluate("document.getElementById('session-status').textContent")

    def upload(self,kind,path,success=True):
        self.chrome.evaluate("document.getElementById('session-status').textContent='waiting'")
        self.chrome.upload('#import-'+kind,path)
        self.chrome.wait(lambda:self.status()!='waiting')
        self.assertTrue(self.status().startswith('Imported' if success else 'Rejected'),self.status())

    def download(self,kind):
        suffix='csv' if kind=='shortlist-csv' else 'json'
        stem='shortlist' if suffix=='csv' else kind
        path=self.root/('valpas-'+stem+'.'+suffix)
        if path.exists():path.unlink()
        self.click('#download-'+kind)
        self.chrome.wait(lambda:path.exists() and not list(self.root.glob('*.crdownload')))
        return path

    def select(self,q,c):
        self.chrome.evaluate("""(() => {
          const section=n=>[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith(n));
          const click=(n,id)=>[...section(n).querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id).click();
          click('4',%s);click('5',%s);
        })()"""%(json.dumps(q),json.dumps(c)))

    def test_actual_download_restore_b1_state_decisions_abstain_and_hostile_notes(self):
        result=b1_result();settings=ReportSettings(max_interactive_depth=3)
        report=self.open_report(result,settings);self.select('M01','P01')
        hostile='=cmd\n</script><script>globalThis.pwned=true</script> Ω\u2028'
        self.chrome.evaluate("""(() => {
          const change=(s,v)=>{const n=document.querySelector(s);n.value=v;n.dispatchEvent(new Event('change'));};
          const field=(s,label)=>[...document.querySelector(s).options].find(o=>o.textContent.startsWith(label)).value;
          change('.metadata-color',field('.metadata-color','condition'));
          change('.metadata-group',field('.metadata-group','condition'));
          change('.sample-order','metadata');change('.diagnostic-h','1');
          document.querySelector('.omission-preview').click();
          const fraction=document.querySelector('.group-fraction');fraction.checked=false;fraction.dispatchEvent(new Event('change'));
          change('#profile-layer','0');change('#query-order','id_desc');change('#candidate-order','id_desc');
          [...document.querySelectorAll('button')].find(b=>b.textContent==='Pin candidate in this view').click();
          const toggle=document.querySelector('.controls input[type=checkbox]');toggle.checked=false;toggle.dispatchEvent(new Event('change'));
          change('#depth','2');
          const search=document.querySelector('#query-search');search.value='M01';search.dispatchEvent(new Event('input'));
          const cs=document.querySelector('#candidate-search');cs.value='P01';cs.dispatchEvent(new Event('input'));
          const notes=document.querySelector('#session-notes');notes.value=%s;notes.dispatchEvent(new Event('input'));
          document.querySelector('#decision-rationale').value=%s;
        })()"""%(json.dumps(hostile),json.dumps(hostile)))
        for action in ('investigate','retain_alternative','abstain'):
            self.chrome.evaluate("document.querySelector('#decision-action').value="+json.dumps(action))
            self.click('#record-decision');self.chrome.wait(lambda:'recorded' in self.status())
            self.chrome.evaluate("document.querySelector('#session-status').textContent='next'")
        session_path=self.download('session');short_path=self.download('shortlist');csv_path=self.download('shortlist-csv')
        session=load_session(session_path,result=result,settings=settings);short=load_shortlist(short_path,result=result,settings=settings)
        doc=session.to_dict();self.assertEqual(doc['notes'],hostile);self.assertEqual(len(doc['decisions']),3)
        self.assertIsNone(doc['decisions'][2]['candidate_id']);self.assertIsNone(doc['decisions'][2]['view']['candidate'])
        self.assertEqual(doc['view']['layers'][0]['h'],1);self.assertTrue(doc['view']['layers'][0]['omission'])
        self.assertFalse(doc['view']['layers'][0]['include_fraction']);self.assertEqual(doc['view']['selectedLayer'],'measured')
        self.assertEqual(doc['view']['queryOrder'],'id_desc');self.assertEqual(doc['view']['pins'],['P01'])
        self.assertEqual(doc['decisions'],short.to_dict()['decisions'])
        self.assertNotIn('</script>',session_path.read_text());self.assertFalse(self.chrome.evaluate('Boolean(globalThis.pwned)'))
        rows=list(csv.reader(io.StringIO(csv_path.read_text())));self.assertEqual(len(rows),4)
        self.assertTrue(all(cell.startswith("'") for row in rows[1:] for cell in row))
        # A new page has no local-storage fallback. Restore the actual downloaded file.
        self.chrome.open(report);self.assertEqual(self.chrome.evaluate("document.querySelector('#session-notes').value"),'')
        self.upload('session',session_path);self.upload('session',session_path)
        self.assertEqual(self.chrome.evaluate("document.querySelector('.diagnostic-h').value"),'1')
        self.assertEqual(self.chrome.evaluate("document.querySelector('#query-order').value"),'id_desc')
        self.assertEqual(self.chrome.evaluate("document.querySelector('.sample-order').value"),'metadata')
        self.assertEqual(self.chrome.evaluate("document.querySelector('#session-notes').value"),hostile)
        restored=load_session(self.download('session'),result=result,settings=settings)
        self.assertEqual(restored,session)
        self.chrome.open(report);self.upload('shortlist',short_path);self.upload('shortlist',short_path)
        self.assertEqual(load_shortlist(self.download('shortlist'),result=result,settings=settings),short)
        self.assertFalse(self.chrome.evaluate('Boolean(globalThis.pwned)'))
        self.assertFalse(self.chrome.evaluate("Boolean(document.querySelector('script[src],link[href],img,iframe'))"))

    def test_actual_file_rejections_are_atomic_scope_binding_nested_unknown_and_tamper(self):
        r=b1_result();settings=ReportSettings(max_interactive_depth=2);s=chosen(r,settings)
        report=self.open_report(replace(r,initial_session=s),settings)
        mutations=[lambda d:d.update(notes='tampered'),lambda d:d.update(comparison_id='wrong'),
                   lambda d:d.update(content_id='0'*64),lambda d:d['view'].update(extra=1),
                   lambda d:d['view']['layers'][0].update(extra=1),lambda d:d['view'].update(query='unknown'),
                   lambda d:d['scope'].update(max_depth=1),lambda d:d['view'].update(depth=999)]
        for i,mutate in enumerate(mutations):
            d=s.to_dict();mutate(d)
            if i:d=seal(d)
            p=self.root/('bad'+str(i)+'.json');p.write_text(json.dumps(d))
            self.upload('session',p,False)
            self.assertEqual(self.chrome.evaluate("document.querySelector('#session-notes').value"),s.to_dict()['notes'])
        p=self.root/'duplicate.json';p.write_text(s.to_json().replace('"notes":','"notes":"x","notes":'))
        self.upload('session',p,False)
        p=s.write(self.root/'good.json');self.open_report(r,ReportSettings(query_ids=('M02',),max_interactive_depth=1),name='narrow.html')
        self.upload('session',p,False);self.assertIn('scope',self.status())

    def test_hostile_exact_ids_survive_real_download_and_upload(self):
        from test_a1_contracts import descriptor
        from valpas.comparison import load_comparison_input, compare_results
        q='001';c=' \t=SUM(A1:A2)</script> Ω';outputs=[]
        for oid in ('a','b'):
            d=descriptor(oid);d['query_ids']=[q];d['candidate_ids']=[c]
            d['data']['inline']={'row_ids':[q],'column_ids':[c],'values':[[1]]}
            outputs.append(load_comparison_input(d))
        r=compare_results(outputs);report=self.open_report(r);self.select(q,c)
        self.chrome.evaluate("document.getElementById('decision-rationale').value='Exact identifiers, not formulas'")
        self.click('#record-decision');self.chrome.wait(lambda:'recorded' in self.status())
        for kind,loader in (('session',load_session),('shortlist',load_shortlist)):
            path=self.download(kind);original=loader(path,result=r)
            self.assertEqual(original.to_dict()['decisions'][0]['query_id'],q)
            self.assertEqual(original.to_dict()['decisions'][0]['candidate_id'],c)
            self.chrome.open(report);self.upload(kind,path)
            self.assertEqual(loader(self.download(kind),result=r),original)
        rows=list(csv.reader(io.StringIO(self.download('shortlist-csv').read_text())))
        self.assertEqual(rows[1][2],"'"+q);self.assertEqual(rows[1][3],"'"+c)

    def test_reference_endpoint_filter_and_shortlist_scope_survive_actual_files(self):
        r=reference_result();settings=ReportSettings(max_interactive_depth=2,pinned_candidate_ids=('c',))
        report=self.open_report(r,settings);self.select('q1','a')
        self.chrome.evaluate("""(() => {for(const [id,value] of [['reference-endpoint','pathway'],['evidence-filter','supported']]){const n=document.getElementById(id);n.value=value;n.dispatchEvent(new Event('change'));}document.getElementById('decision-rationale').value='Source-specific support only';})()""")
        self.click('#record-decision');self.chrome.wait(lambda:'recorded' in self.status())
        path=self.download('shortlist');short=load_shortlist(path,result=r,settings=settings)
        self.assertEqual(short.to_dict()['view']['referenceEndpoint'],'pathway')
        self.assertEqual(short.to_dict()['view']['evidenceFilter'],'supported')
        self.chrome.open(report);self.upload('shortlist',path)
        self.assertEqual(self.chrome.evaluate("document.getElementById('reference-endpoint').value"),'pathway')
        self.assertEqual(self.chrome.evaluate("document.getElementById('evidence-filter').value"),'supported')
        self.assertEqual(load_shortlist(self.download('shortlist'),result=r,settings=settings),short)


if __name__=='__main__':unittest.main()
