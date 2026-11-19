"""Actual installed B2 offline downloads/imports; stdlib CDP, no source imports."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET


def helper(name):
    # Python -I excludes script directories. Load only these explicitly copied,
    # sdist-inventoried harness helpers; never insert a package/source search path.
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate(chrome_path, bundle, directory):
    from valpas.comparison import load_comparison_bundle, load_session, load_shortlist
    smoke = helper('distribution_smoke')
    require = smoke.require
    result = load_comparison_bundle(bundle)
    directory.mkdir()
    report = directory / 'standalone.html'
    shutil.copy2(bundle / 'report.html', report)
    chrome = helper('chrome_cdp').ChromeCDP(str(chrome_path), directory)
    files = {}

    def click(selector):
        chrome.evaluate('document.querySelector(' + json.dumps(selector) + ').click()')

    def status():
        return chrome.evaluate("document.getElementById('session-status').textContent")

    def download(kind, label):
        suffix = 'csv' if kind == 'shortlist-csv' else 'svg' if kind == 'figure' else 'json'
        stem = 'shortlist' if suffix == 'csv' else 'query-figure' if kind == 'figure' else kind
        path = directory / ('valpas-' + stem + '.' + suffix)
        require(not path.exists(), 'previous download not archived')
        click('.download-query-figure' if kind == 'figure' else '#download-' + kind)
        chrome.wait(lambda: path.exists() and not list(directory.glob('*.crdownload')))
        saved = directory / (label + '.' + suffix)
        path.rename(saved)
        files[label] = {'path': str(saved), 'sha256': smoke.hashlib.sha256(saved.read_bytes()).hexdigest()}
        return saved

    def upload(kind, path, accepted=True):
        chrome.evaluate("document.getElementById('session-status').textContent='waiting'")
        chrome.upload('#import-' + kind, path)
        chrome.wait(lambda: status() != 'waiting')
        require(status().startswith('Imported' if accepted else 'Rejected'), status())

    try:
        chrome.open(report)
        require(chrome.evaluate("document.getElementById('session-notes').value") == result.initial_session.to_dict()['notes'],
                'inventoried initial session not restored')
        # Capture scientific payload and complete nomination rows, then filter
        # actual DOM rows by independent evidence endpoints and restore them.
        chrome.evaluate(r"""(() => {
          const check=(v,m)=>{if(!v)throw Error(m);};
          const section=n=>[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith(n));
          const select=(n,id)=>[...section(n).querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id).click();
          const change=(id,value)=>{const s=document.getElementById(id);s.value=value;s.dispatchEvent(new Event('change'));};
          select('4','M01');select('5','P01');
          window.originalPayload=document.getElementById('comparison-data').textContent;
          window.originalOverview=section('2').innerHTML;
          const rows=()=>[...section('5').querySelectorAll('tr.selectable')].map(r=>r.cells[0].textContent).join(',');
          const ranks=()=>[...section('5').querySelectorAll('tr.selectable')].map(r=>r.innerHTML).join('');
          const original=ranks();check(rows()==='P01,P02,P03','full nomination union');
          change('reference-endpoint','direct');change('evidence-filter','supported');check(rows()==='P01','direct support');
          change('reference-endpoint','inferred');check(rows()==='P02','inferred separate');
          change('reference-endpoint','pathway');check(rows()==='P03','pathway separate');
          change('reference-endpoint','direct');change('evidence-filter','unsupported');check(rows()==='P02,P03','unsupported display');
          change('evidence-filter','all');check(ranks()===original,'rank cells changed by reference filter');
          change('evidence-filter','supported');select('5','P01');
          check(document.getElementById('comparison-data').textContent===window.originalPayload,'payload mutated');
          check(section('2').innerHTML===window.originalOverview,'overview denominators mutated');
          check(!document.querySelector('script[src],link[href],img,iframe'),'external resources');
        })()""")
        notes = '=cmd\n</script><script>globalThis.b2Pwned=true</script> Ω'
        chrome.evaluate(r"""(() => {
          const change=(s,v)=>{const n=document.querySelector(s);n.value=v;n.dispatchEvent(new Event('change'));};
          const field=s=>[...document.querySelector(s).options].find(o=>o.textContent.startsWith('condition')).value;
          change('.metadata-color',field('.metadata-color'));change('.metadata-group',field('.metadata-group'));
          change('.sample-order','metadata');change('.diagnostic-h','1');document.querySelector('.omission-preview').click();
          const n=document.getElementById('session-notes');n.value=%s;n.dispatchEvent(new Event('input'));
          document.getElementById('decision-rationale').value=%s;
        })()""" % (json.dumps(notes), json.dumps(notes)))
        for action in ('investigate', 'retain_alternative', 'abstain'):
            chrome.evaluate("document.getElementById('decision-action').value=" + json.dumps(action))
            click('#record-decision')
            chrome.wait(lambda: 'recorded' in status())
            chrome.evaluate("document.getElementById('session-status').textContent='next'")
        session_path = download('session', 'session-original')
        shortlist_path = download('shortlist', 'shortlist-original')
        csv_path = download('shortlist-csv', 'shortlist-spreadsheet')
        session = load_session(session_path, result=result)
        shortlist = load_shortlist(shortlist_path, result=result)
        doc = session.to_dict()
        require(doc['notes'] == notes and len(doc['decisions']) == 5, 'notes or decisions lost')
        require(doc['decisions'][-1]['candidate_id'] is None and doc['decisions'][-1]['view']['candidate'] is None,
                'query-level abstention lost')
        require(doc['view']['referenceEndpoint'] == 'direct' and doc['view']['evidenceFilter'] == 'supported', 'reference state lost')
        layer = doc['view']['layers'][0]
        require(layer['h'] == 1 and layer['omission'] and layer['color'] == layer['group'] == 'condition', 'B1 state lost')
        require(shortlist.to_dict()['decisions'] == doc['decisions'], 'shortlist decisions differ')
        with csv_path.open(newline='') as handle:
            rows = list(csv.reader(handle))
        require(len(rows) == 6 and all(c.startswith("'") for row in rows[1:] for c in row), 'CSV safety/count')
        for kind, path, loader, original in (('session', session_path, load_session, session),
                                               ('shortlist', shortlist_path, load_shortlist, shortlist)):
            chrome.open(report)
            upload(kind, path)
            upload(kind, path)
            require(chrome.evaluate("document.getElementById('session-notes').value") == notes, 'notes not restored')
            require(chrome.evaluate("document.getElementById('evidence-filter').value") == 'supported', 'filter not restored')
            require(chrome.evaluate("document.querySelector('.sample-order').value") == 'metadata', 'B1 order not restored')
            restored = download(kind, kind + '-restored')
            require(loader(restored, result=result) == original, 'actual download/import roundtrip differs')
        # Invalid bytes must not replace current state; assert atomic browser rejection.
        bad = directory / 'tampered-session.json'
        bad.write_text(json.dumps(doc | {'notes': 'tampered'}))
        upload('session', bad, False)
        require(chrome.evaluate("document.getElementById('session-notes').value") == notes, 'rejected import mutated state')
        figure = download('figure', 'browser-figure')
        files['browser-figure'] = smoke.check_figure(figure, browser=True)
        root = ET.parse(figure).getroot()
        ns = '{http://www.w3.org/2000/svg}'
        plots = root.findall(ns + 'svg')
        require(len(plots) == 2 and len(plots[0].findall(ns + 'circle')) == 6, 'browser scatter cohort')
        imputed = [n for n in plots[1].findall(ns + 'circle') if 'imputed' in n.attrib.get('class', '')]
        require(len(imputed) == 0 and len(plots[1].findall(ns + 'circle')) == 12, 'observed profile masks')
        require(notes in ''.join(root.itertext()), 'literal notes missing from SVG')
        require(chrome.evaluate("!new DOMParser().parseFromString(" + json.dumps(figure.read_text()) + ",'image/svg+xml').querySelector('parsererror')"), 'Chrome XML parser rejected SVG')
        require(not chrome.evaluate('Boolean(globalThis.b2Pwned)'), 'hostile text executed')
        require(chrome.evaluate("document.getElementById('comparison-data').textContent") == (bundle / 'report_payload.json').read_text(),
                'download/import changed scientific payload')
        return {'status': 'passed', 'uri': report.as_uri(), 'report_sha256': smoke.hashlib.sha256(report.read_bytes()).hexdigest(),
                'transport': 'file://; external hostname resolution disabled; CSP connect-src none; local CDP only',
                'actions': ['independent reference filters/rank and denominator invariant', 'initial session restore',
                            'three user decisions including query abstention', 'hostile notes inert',
                            'actual session/shortlist/CSV downloads', 'actual file imports twice and exact restore',
                            'atomic tampered-file rejection', 'actual SVG download; Python and Chrome XML parse; masks/caption'],
                'files': files, 'decision_count': 5}
    finally:
        chrome.close()


if __name__ == '__main__':
    chrome, bundle, directory, destination = map(Path, sys.argv[1:])
    record = validate(chrome, bundle, directory)
    destination.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record, indent=2))
