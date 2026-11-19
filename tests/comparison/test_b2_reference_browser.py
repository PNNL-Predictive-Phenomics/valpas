"""Actual direct-file Chrome reference controls, with no server/dependency install."""
from dataclasses import replace
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_a3_browser import CHROME
from test_b2_reference import fixture_result
from valpas.comparison import ReferenceData, ReportSettings
from valpas.comparison.browser import render_report


@unittest.skipUnless(CHROME,'Existing Chrome required for actual offline interaction')
class ReferenceBrowserCase(unittest.TestCase):
    def chrome(self,html,checks):
        script='<script>try {const assert=(v,m)=>{if(!v)throw Error(m);};'+checks+";document.body.setAttribute('data-reference-test','passed');}catch(e){document.body.setAttribute('data-reference-test','FAILED '+e.message);}</script>"
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'report.html';p.write_text(html.replace('</body>',script+'</body>'))
            proc=subprocess.run([CHROME,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
                '--disable-background-networking','--disable-component-update','--disable-sync',
                '--host-resolver-rules=MAP * ~NOTFOUND','--user-data-dir='+str(root/'chrome'),'--dump-dom',p.as_uri()],
                capture_output=True,text=True,timeout=60)
            self.assertEqual(proc.returncode,0,proc.stderr[-2000:])
            self.assertIn('data-reference-test="passed"',proc.stdout,proc.stdout[-6000:]+proc.stderr[-1000:])

    def test_evidence_filter_endpoint_depth_output_and_pins_preserve_nominations(self):
        r=fixture_result();raw=r.references.to_dict()
        raw['endpoints'][0]['description']='</script><script>globalThis.pwned=true</script> Ω'
        raw['evidence'][0]['description']='</script><script>globalThis.pwned=true</script> Ω'
        r=replace(r,references=ReferenceData.from_dict(raw))
        html,_,_=render_report(r,ReportSettings(max_interactive_depth=2,pinned_candidate_ids=('c',)))
        self.chrome(html,r"""
        assert(document.documentElement.dataset.reportReady==='true','initial render');
        assert(!globalThis.pwned,'hostile reference executed');
        const data=JSON.parse(document.getElementById('comparison-data').textContent);
        const original=JSON.stringify(data);
        const sections=[...document.querySelectorAll('main > section')];
        const query=sections.find(s=>s.querySelector('h2').textContent.startsWith('4'));
        const workspace=sections.find(s=>s.querySelector('h2').textContent.startsWith('5'));
        const refs=sections.find(s=>s.querySelector('h2').textContent.startsWith('6'));
        assert(refs.textContent.includes('All-assessed'),'summary cohort disclosure');
        assert(refs.textContent.includes('aggregation_denominator'),'summary denominator');
        const chooseQuery=q=>[...query.querySelectorAll('tr.selectable')].find(t=>t.cells[0].textContent===q).click();
        const candidates=()=>[...workspace.querySelectorAll('tr.selectable')].map(t=>t.cells[0].textContent);
        const filter=value=>{const s=document.getElementById('evidence-filter');s.value=value;s.dispatchEvent(new Event('change'));};
        const endpoint=value=>{const s=document.getElementById('reference-endpoint');s.value=value;s.dispatchEvent(new Event('change'));};
        chooseQuery('q1');
        assert(candidates().join(',')==='a,b,c','default candidate union/pin');
        filter('supported');assert(candidates().join(',')==='a','direct evidence filtering');
        workspace.querySelector('tr.selectable').click();
        assert(workspace.textContent.includes('second-record'),'one-to-many records inspectable');
        assert(workspace.textContent.includes('reference_status'),'candidate evidence column');
        endpoint('inferred');assert(candidates().join(',')==='b','direct/inferred not unioned');
        endpoint('pathway');assert(candidates().join(',')==='c','pathway independent pinned evidence');
        endpoint('other-source');assert(candidates().length===0,'source independent and bounded');
        endpoint('direct');filter('unsupported');assert(candidates().join(',')==='b,c','unsupported by source only');
        chooseQuery('qN');assert(candidates().length===0,'unassessed is not unsupported');
        filter('all');assert(candidates().length===3,'unassessed nominations retained');
        chooseQuery('q1');filter('supported');
        const depth=document.getElementById('depth');depth.value=1;depth.dispatchEvent(new Event('change'));
        assert(candidates().join(',')==='a','depth evidence filter');
        const toggle=document.querySelector('.controls input[type=checkbox]');toggle.checked=false;toggle.dispatchEvent(new Event('change'));
        assert(candidates().join(',')==='a','hidden output does not redefine union');
        filter('all');assert(candidates().join(',')==='a,b,c','nominations retained after filters');
        assert(JSON.stringify(JSON.parse(document.getElementById('comparison-data').textContent))===original,'payload nominations/science mutated');
        assert(!globalThis.pwned,'hostile text executed after interactions');
        assert(!document.querySelector('script[src],link[href],img,iframe'),'external resources');
        """)

    def test_subset_full_cohort_and_metadata_omission_direct_file(self):
        for omitted in (False,True):
            html,_,_=render_report(fixture_result(),ReportSettings(query_ids=('q1',),max_interactive_depth=1,omit_metadata=omitted))
            self.chrome(html,r"""
            const sections=[...document.querySelectorAll('main > section')];
            const query=sections.find(s=>s.querySelector('h2').textContent.startsWith('4'));
            const workspace=sections.find(s=>s.querySelector('h2').textContent.startsWith('5'));
            const refs=sections.find(s=>s.querySelector('h2').textContent.startsWith('6'));
            const data=JSON.parse(document.getElementById('comparison-data').textContent);
            assert(query.querySelectorAll('tr.selectable').length===6,'full query cohort');
            if(data.references) {
              assert(refs.querySelectorAll('tr.selectable').length===12,'full query/output reference rows');
              [...refs.querySelectorAll('tr.selectable')].find(t=>t.textContent.includes('q6')).click();
              assert(workspace.textContent.includes('outside embedded detail scope'),'full cohort drilldown scope');
            } else {
              assert(refs.textContent.includes('omitted from HTML'),'reference omission disclosure');
              assert(!document.getElementById('reference-endpoint'),'no omitted controls');
            }
            """)


if __name__=='__main__':unittest.main()
