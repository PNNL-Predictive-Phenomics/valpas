"""Real file:// Chrome smoke, using only stdlib and an already installed browser."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_a3_report import profile_layer, profiled_result, fixture_result
from valpas.comparison import ReportSettings
from valpas.comparison.browser import render_report

CHROME = shutil.which('chromium') or shutil.which('google-chrome')
if not CHROME and Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome').is_file():
    CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'


@unittest.skipUnless(CHROME, 'No existing Chrome/Chromium; see manual offline checklist')
class OfflineBrowserCase(unittest.TestCase):
    def test_no_profile_and_subset_reports_open_directly(self):
        for omitted in (False, True):
            html, _, _ = render_report(fixture_result(), ReportSettings(query_ids=('M01',), max_interactive_depth=1, omit_metadata=omitted))
            script = """<script>
            try {
              const sections=[...document.querySelectorAll('main > section')];
              const queries=sections.find(s=>s.querySelector('h2').textContent.startsWith('4'));
              const workspace=sections.find(s=>s.querySelector('h2').textContent.startsWith('5'));
              const row=id=>[...queries.querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id);
              row('M02').click();
              if(!workspace.textContent.includes('outside embedded detail scope'))throw Error('scope');
              row('M01').click(); workspace.querySelector('tr.selectable').click();
              if(!workspace.textContent.includes('No profile layers embedded'))throw Error('no profile');
              document.body.setAttribute('data-smoke','passed');
            } catch(e) {document.body.setAttribute('data-smoke',e.message);}
            </script>"""
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'report.html';p.write_text(html.replace('</body>',script+'</body>'))
                result=subprocess.run([CHROME,'--headless','--disable-gpu','--no-first-run',
                    '--disable-background-networking','--host-resolver-rules=MAP * ~NOTFOUND',
                    '--user-data-dir='+str(Path(tmp)/'chrome'),'--dump-dom',p.as_uri()],
                    capture_output=True,text=True,timeout=60)
                self.assertEqual(result.returncode,0,result.stderr[-1000:])
                self.assertIn('data-smoke="passed"',result.stdout,result.stdout[-3000:])

    def test_real_file_offline_interactions_and_hostile_labels(self):
        layer = profile_layer()
        layer['features'][0]['label'] = '</script><script>globalThis.pwned=true</script>\u2028Ω'
        report, _, _ = render_report(profiled_result(layer), ReportSettings(max_interactive_depth=3))
        checks = r"""
<script>
(() => {
  const assert = (v,m) => {if(!v) throw Error(m);};
  const clickRow = (parent,id) => {
    const row = [...parent.querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id);
    assert(row,'missing row '+id); row.click();
  };
  try {
    assert(document.documentElement.dataset.reportReady==='true','initial render');
    assert(!globalThis.pwned,'hostile label executed');
    assert(document.querySelectorAll('svg').length===1,'overview depth plot');
    const heat=document.querySelector('.heat button'); assert(heat,'heatmap'); heat.click();
    assert(document.body.textContent.includes('Selected output pair:'),'heatmap drilldown');
    const querySection=[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith('4'));
    clickRow(querySection,'M01');
    const workspace=[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith('5'));
    clickRow(workspace,'P01');
    assert(workspace.querySelectorAll('svg').length===2,'scatter and sample profiles');
    assert(workspace.querySelectorAll('circle.imputed').length===2,'imputed marks distinct');
    assert(workspace.textContent.includes('Jointly observed finite points: 4'),'joint observed denominator');
    assert([...workspace.querySelectorAll('svg title')].some(t=>t.textContent.includes('S01')),'hover observation IDs');
    const pin=[...workspace.querySelectorAll('button')].find(b=>b.textContent==='Pin candidate in this view');pin.click();
    assert(workspace.textContent.includes('Unpin candidate'),'pin interaction');
    const input=document.getElementById('candidate-search');input.value='synthetic annotation';input.dispatchEvent(new Event('input'));
    assert(workspace.querySelectorAll('tr.selectable').length===3,'annotation search');
    input.value='outside-scope';input.dispatchEvent(new Event('input'));
    assert(workspace.textContent.includes('0 candidates shown'),'out of scope search');
    const q=document.getElementById('query-search');q.value='M02';q.dispatchEvent(new Event('input'));
    assert(querySection.querySelectorAll('tr.selectable').length===1,'query search');
    querySection.querySelector('th button').click();
    const depth=document.getElementById('depth');depth.value=1;depth.dispatchEvent(new Event('change'));
    assert(document.querySelector('.heat').textContent.includes('evaluable'),'depth selection');
    const toggle=document.querySelector('.controls input[type=checkbox]');toggle.checked=false;toggle.dispatchEvent(new Event('change'));
    assert(document.querySelectorAll('.heat button').length===1,'display-only hide output');
    assert(!globalThis.pwned,'hostile text remained inert');
    assert(!document.querySelector('script[src],link[href],img,iframe'),'no external resources');
    document.body.setAttribute('data-smoke','passed');
  } catch(e) {document.body.setAttribute('data-smoke','FAILED: '+e.message);}
})();
</script>
"""
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); html=root/'report.html'; html.write_text(report.replace('</body>',checks+'</body>'),encoding='utf-8')
            command=[CHROME,'--headless','--disable-gpu','--no-first-run','--no-default-browser-check',
                     '--disable-background-networking','--disable-component-update','--disable-sync',
                     '--host-resolver-rules=MAP * ~NOTFOUND', '--user-data-dir='+str(root/'chrome'),
                     '--dump-dom',html.as_uri()]
            result=subprocess.run(command,capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stderr[-2000:])
            self.assertIn('data-smoke="passed"',result.stdout,result.stdout[-5000:]+'\n'+result.stderr[-2000:])


if __name__=='__main__': unittest.main()
