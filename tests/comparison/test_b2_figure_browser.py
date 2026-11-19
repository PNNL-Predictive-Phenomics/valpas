"""Actual offline Chrome SVG downloads, parsed as XML, with B1/session parity."""
import json
from pathlib import Path
import tempfile
import unittest

from chrome_cdp import ChromeCDP
from test_a3_browser import CHROME
from test_b1_persistence import b1_result
from test_b2_figures import HOSTILE, SVG, assert_safe_svg, hostile_result
from valpas.comparison import ReportSettings, load_session
from valpas.comparison.browser import render_report


@unittest.skipUnless(CHROME, 'Existing Chrome required for actual figure download')
class FigureBrowserCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.chrome = ChromeCDP(CHROME, self.root); self.addCleanup(self.chrome.close)

    def open(self, result, q, c, settings=None):
        report = self.root/'report.html'; report.write_text(render_report(result, settings)[0])
        self.chrome.open(report)
        self.chrome.evaluate('''(() => {
          const section=n=>[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith(n));
          const click=(n,id)=>[...section(n).querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id).click();
          click('4',%s);click('5',%s);
        })()''' % (json.dumps(q), json.dumps(c)))
        return report

    def download(self):
        path = self.root/'valpas-query-figure.svg'
        if path.exists(): path.unlink()
        self.chrome.evaluate("document.querySelector('.download-query-figure').click()")
        self.assertNotIn('rejected', self.chrome.evaluate("document.querySelector('.figure-status').textContent"))
        self.chrome.wait(lambda: path.exists() and not list(self.root.glob('*.crdownload')))
        return path

    def test_actual_download_hostile_ids_annotations_notes_same_and_cross(self):
        for same in (False, True):
            r, q, c, layer = hostile_result(same)
            self.open(r, q, c)
            self.chrome.evaluate("const notes=document.querySelector('#session-notes');notes.value="+json.dumps(HOSTILE)+";notes.dispatchEvent(new Event('input'))")
            root, caption = assert_safe_svg(self, self.download())
            for value in (q, c, layer, HOSTILE, 'User notes: ' + HOSTILE,
                          'bounded embedded scope', 'Not identical to Python', 'not model attribution'):
                self.assertIn(value, caption)
            self.assertTrue(root.findall('.//' + SVG + 'circle'))
            self.assertFalse(self.chrome.evaluate('Boolean(globalThis.pwned)'))
            self.assertEqual(self.chrome.evaluate("document.querySelectorAll('script[src],link[href],img,iframe').length"), 0)
            # Real Chrome's XML parser also accepts the downloaded bytes.
            self.assertTrue(self.chrome.evaluate("!new DOMParser().parseFromString("+json.dumps((self.root/'valpas-query-figure.svg').read_text())+",'image/svg+xml').querySelector('parsererror')"))

    def test_actual_download_preserves_b1_controls_masks_and_strict_session(self):
        r = b1_result(); settings = ReportSettings(max_interactive_depth=3)
        self.open(r, 'M01', 'P01', settings)
        self.chrome.evaluate('''(() => {
          const change=(s,v)=>{const n=document.querySelector(s);n.value=v;n.dispatchEvent(new Event('change'));};
          const field=s=>[...document.querySelector(s).options].find(o=>o.textContent.startsWith('condition')).value;
          change('.metadata-color',field('.metadata-color'));change('.metadata-group',field('.metadata-group'));
          change('.sample-order','metadata');change('.diagnostic-h','1');document.querySelector('.omission-preview').click();
        })()''')
        root, caption = assert_safe_svg(self, self.download())
        self.assertIn('jointly observed finite: 4', caption)
        self.assertIn('Query observed finite: 4; finite originally unobserved: 1', caption)
        self.assertIn('"h":1', caption); self.assertIn('"omission":true', caption)
        self.assertIn('"group":"condition"', caption)
        self.assertIn('marginal group summary', caption)
        plots = root.findall(SVG+'svg')
        self.assertEqual(len(plots), 2)
        self.assertEqual(len(plots[0].findall(SVG+'circle')), 4)
        self.assertEqual(len(plots[1].findall(SVG+'circle')), 10)
        imputed = [n for n in plots[1].findall(SVG+'circle') if 'imputed' in n.attrib.get('class', '')]
        self.assertEqual(len(imputed), 2)
        self.assertTrue(all('stroke:' in n.attrib['style'] for n in imputed))
        self.chrome.evaluate("document.getElementById('download-session').click()")
        path = self.root/'valpas-session.json'; self.chrome.wait(lambda: path.exists() and not list(self.root.glob('*.crdownload')))
        session = load_session(path, result=r, settings=settings)
        layer = session.to_dict()['view']['layers'][0]
        self.assertEqual(layer['h'], 1); self.assertTrue(layer['omission'])
        self.assertEqual(layer['color'], 'condition'); self.assertEqual(layer['group'], 'condition')
        self.assertNotIn('figure', session.to_dict()['view'])

    def test_invalid_xml_notes_rejected_without_download(self):
        self.open(b1_result(), 'M01', 'P01')
        self.chrome.evaluate("const n=document.querySelector('#session-notes');n.value='bad'+String.fromCharCode(1);n.dispatchEvent(new Event('input'));document.querySelector('.download-query-figure').click()")
        self.assertIn('XML 1.0', self.chrome.evaluate("document.querySelector('.figure-status').textContent"))
        self.assertFalse((self.root/'valpas-query-figure.svg').exists())


if __name__ == '__main__': unittest.main()
