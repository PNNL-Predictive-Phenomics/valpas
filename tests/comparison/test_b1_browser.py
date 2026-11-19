"""B1 actual Chrome/file:// parity and UI tests; stdlib, no server or downloads."""
import copy
from html.parser import HTMLParser
import json
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_a3_browser import CHROME
from test_a3_report import fixture_result, profile_layer, profiled_result
from test_b1_diagnostics import DATA, metadata_doc, raw_layer
from valpas.comparison import ReportSettings
from valpas.comparison.browser import build_report_payload, render_report, safe_json
from valpas.comparison.diagnostics import SampleMetadata, covariance_diagnostic, group_summary
from valpas.comparison.profiles import ProfileData


class OutputParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'pre' and dict(attrs).get('id') == 'b1-test-result':
            self.active = True

    def handle_endtag(self, tag):
        if tag == 'pre':
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def report_with_payload(result, mutate=None):
    """Exercise the real renderer, replacing ONLY its inert escaped JSON data.

    This permits sample_metadata injection until the parent integrates the key.
    The renderer and build_report_payload must still agree on all base content.
    """
    settings = ReportSettings(max_interactive_depth=3)
    report, original, _ = render_report(result, settings)
    payload = build_report_payload(result, settings)
    assert payload == original
    if mutate:
        mutate(payload)
    marker = '<script id="comparison-data" type="application/json">'
    # Do not globally replace user strings or HTML script closers.
    start = report.index(marker) + len(marker)
    end = report.index('</script>', start)
    return report[:start] + safe_json(payload) + report[end:], payload


JS_HELPERS = r"""
const assert=(value,message)=>{if(!value)throw Error(message);};
const compare=(actual,expected,path='root')=>{
  if(typeof expected==='number') {
    assert(typeof actual==='number' && Number.isFinite(actual),path+': not finite number');
    assert(Math.abs(actual-expected)<=Math.max(1e-12*Math.abs(expected),1e-300),path+': '+actual+' != '+expected);
  } else if(expected===null || typeof expected!=='object') assert(actual===expected,path+': value');
  else if(Array.isArray(expected)) {
    assert(Array.isArray(actual)&&actual.length===expected.length,path+': array length');
    expected.forEach((v,i)=>compare(actual[i],v,path+'['+i+']'));
  } else {
    assert(actual!==null&&typeof actual==='object'&&!Array.isArray(actual),path+': object');
    assert(JSON.stringify(Object.keys(actual).sort())===JSON.stringify(Object.keys(expected).sort()),path+': exact keys');
    Object.keys(expected).forEach(k=>compare(actual[k],expected[k],path+'.'+k));
  }
};
const section=n=>[...document.querySelectorAll('main > section')].find(s=>s.querySelector('h2').textContent.startsWith(n));
const clickRow=(parent,id)=>{const row=[...parent.querySelectorAll('tr.selectable')].find(r=>r.cells[0].textContent===id);assert(row,'missing row '+id);row.click();};
const selectPair=()=>{clickRow(section('4'),'M01');clickRow(section('5'),'P01');return section('5');};
const change=(node,value)=>{node.value=value;node.dispatchEvent(new Event('change'));};
const exact=selector=>JSON.parse(document.querySelector(selector+' pre').textContent);
"""


@unittest.skipUnless(CHROME, 'No existing Chrome/Chromium; actual browser required')
class B1BrowserCase(unittest.TestCase):
    def chrome(self, report, script, inputs=None):
        harness = ('<script>\ntry {\n' + JS_HELPERS + '\nconst inputs=JSON.parse(' + safe_json(safe_json(inputs)) + ');\n'
                   + script.replace('</script', '<\\/script') + '\nconst output=document.createElement("pre");'
                   'output.id="b1-test-result";output.textContent=JSON.stringify({ok:true});document.body.append(output);'
                   '\n} catch(error) {const output=document.createElement("pre");output.id="b1-test-result";'
                   'output.textContent=JSON.stringify({ok:false,error:error.stack});document.body.append(output);}\n</script>')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'report.html'
            path.write_text(report.replace('</body>', harness + '</body>'), encoding='utf-8')
            command = [CHROME, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                       '--disable-background-networking', '--disable-component-update', '--disable-sync',
                       '--host-resolver-rules=MAP * ~NOTFOUND', '--user-data-dir=' + str(root / 'chrome'),
                       '--dump-dom', path.as_uri()]
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            parser = OutputParser()
            parser.feed(result.stdout)
            self.assertTrue(parser.parts, result.stdout[-5000:] + result.stderr[-1000:])
            output = json.loads(''.join(parser.parts))
            self.assertTrue(output['ok'], output.get('error'))

    def test_shared_fixture_and_edge_cases_full_dictionary_parity(self):
        cases = []

        def add(name, layer, metadata=None, field='condition', h=5, omission=True, include_fraction=True, ds=None):
            # Validate exactly the same supplied layers as Python, before transport.
            layer = ProfileData([layer]).to_dict()['layers'][0]
            ds = ds or layer['dataset']
            metadata = SampleMetadata.from_dict(metadata or metadata_doc(ds))
            metadata.validate_binding(ds)
            options = {'h': h, 'omission': omission}
            group_options = {'include_fraction': include_fraction}
            cases.append({'name': name, 'layer': layer, 'dataset': ds, 'metadata': metadata.to_dict(),
                          'field': field, 'options': options, 'group_options': group_options,
                          'covariance': covariance_diagnostic(layer, ds, 'Q', 'C', **options),
                          'groups': [group_summary(layer, ds, metadata, ds[role + '_namespace'], fid,
                                                   field, **group_options)
                                     for role, fid in [('query', 'Q'), ('candidate', 'C')]]})

        for case in DATA['cases']:
            add(case['name'], raw_layer(case), h=case['h'], omission=case['omission'])
        add('defaults', raw_layer(), omission=False)
        ds = copy.deepcopy(raw_layer()['dataset'])
        ds['observation_ids'].reverse()
        ds['dataset_evidence']['limitations'] = 'Different explanatory text; identical source fingerprint'
        add('binding comparison semantics and required order', raw_layer(), ds=ds)
        add('h exceeds cohort', raw_layer(), h=99)
        add('fraction not requested', raw_layer(), include_fraction=False)
        add('continuous not a group', raw_layer(), field='age')
        add('missing field', raw_layer(), field='absent')
        empty = metadata_doc(); empty['records'] = []
        add('no known groups', raw_layer(), metadata=empty)
        for count in (0, 1, 2):
            layer = raw_layer()
            for f in layer['features']:
                f['values'] = f['values'][:count] + [None] * (5-count)
            add('joint count ' + str(count), layer)
        layer = raw_layer()
        layer.update(raw_unimputed=False, mask_source='explicit_original')
        layer['features'][0].update(values=[0, 1, 999, 3, 9], observed=[True, True, False, True, True])
        layer['features'][1].update(values=[0, None, 2, 3, 9], observed=[True]*5)
        doc = metadata_doc()
        doc['records'][0]['values'].clear()
        doc['records'][2]['values']['condition'] = None
        doc['records'].pop()
        add('imputed and transformed null; missing group precedence', layer, metadata=doc)
        doc['records'][2]['values']['condition'] = 'B'
        add('disjoint not observed exclusion', layer, metadata=doc)
        for reason in ('missing_feature', 'missing_required_observations', 'original_mask_unavailable'):
            layer = raw_layer()
            if reason == 'missing_feature':
                layer['features'].pop(0)
            elif reason == 'missing_required_observations':
                layer['observation_ids'].pop()
                for f in layer['features']:
                    f['values'].pop()
            else:
                layer.update(raw_unimputed=False, mask_source='unavailable')
            add(reason, layer)
        layer = raw_layer()
        layer['observation_ids'].reverse()
        for f in layer['features']:
            f['values'].reverse()
        add('reordered profile axes', layer)
        layer['subset_extra_observations'] = True
        layer['observation_ids'] += ['😀', '\ue000']
        for f in layer['features']:
            f['values'] += [1e100, 1e100]
        doc = metadata_doc()
        doc['subset_extra_observations'] = True
        doc['records'] += [{'observation_id': sid, 'values': {'condition': 'excluded'}} for sid in ['😀', '\ue000']]
        add('extra cohort Unicode order', layer, metadata=doc)
        doc = metadata_doc()
        for record, group in zip(doc['records'], ['😀', '\ue000', '__proto__', '', 'constructor']):
            record['values']['condition'] = group
        add('arbitrary categorical strings and Unicode group order', raw_layer(), metadata=doc)
        doc = metadata_doc()
        doc['fields']['__proto__'] = 'categorical'
        for record in doc['records']:
            record['values']['__proto__'] = 'constructor'
        add('arbitrary field names', raw_layer(), metadata=doc, field='__proto__')
        numeric_cases = [
            ('deviation overflow', [1e308, -1e308, 1e308, -1e308, 0], [1e308]*4+[-1e308]),
            ('product overflow', [1e200, -1e200, 0, 1, 2], [1e200, -1e200, 0, 1, 2]),
            ('absolute sum overflow but finite stats', [1e154, -1e154, 1e154, -1e154, 0], [1e154, -1e154, 1e154, -1e154, 0]),
            ('scaled correlation', [-1e150, -5e149, 0, 5e149, 1e150], [-1e150, -5e149, 0, 5e149, 1e150]),
            ('retained constant', [1, 1, 1, 1, 9], [0, 1, 2, 3, 9]),
            ('stable cancellation', [1e16, 1, -1e16, 3, 5], [2, 4, 1, 3, 0]),
            ('underflow', [1e-200, -1e-200, 0, 1e-200, 0], [1e-200, -1e-200, 0, 1e-200, 0]),
        ]
        for name, xs, ys in numeric_cases:
            layer = raw_layer()
            layer['features'][0]['values'] = xs
            layer['features'][1]['values'] = ys
            add(name, layer, h=1)
        # Deterministic broad finite inputs exercise summation, masks, grouping and h.
        for seed in range(12):
            layer = raw_layer()
            layer['features'][0]['values'] = [math.sin(seed+i)*10**(seed % 4) for i in range(5)]
            layer['features'][1]['values'] = [math.cos(seed*2+i)*10**(seed % 3) for i in range(5)]
            add('finite sweep '+str(seed), layer, h=seed % 6+1, omission=bool(seed % 2))
        report, _ = report_with_payload(fixture_result())
        self.chrome(report, r"""
assert(document.documentElement.dataset.reportReady==='true','render ready');
assert(Object.keys(window.valpasDiagnostics).sort().join(',')==='covarianceDiagnostic,groupSummary','narrow API');
inputs.forEach(test=>{
  const before=JSON.stringify(test);
  const result=valpasDiagnostics.covarianceDiagnostic(test.layer,test.dataset,'Q','C',test.options);
  compare(result,test.covariance,test.name+'.covariance');
  [['query','Q'],['candidate','C']].forEach(([role,id],i)=>{
    const group=valpasDiagnostics.groupSummary(test.layer,test.dataset,test.metadata,test.dataset[role+'_namespace'],id,test.field,test.group_options);
    compare(group,test.groups[i],test.name+'.group.'+role);
    group.namespace.id='detached';group.required_observation_ids.length=0;
  });
  result.required_observation_ids.length=0;result.products.length=0;
  assert(JSON.stringify(test)===before,'input mutation '+test.name);
});
const first=inputs.find(t=>t.name==='defaults');
compare(valpasDiagnostics.covarianceDiagnostic(first.layer,first.dataset,'Q','C'),first.covariance,'default arguments');
compare(valpasDiagnostics.groupSummary(first.layer,first.dataset,first.metadata,first.dataset.query_namespace,'Q',first.field),first.groups[0],'default fraction');
const mismatch={...first.dataset,dataset_id:'wrong'};
let rejectedBinding=false;try{valpasDiagnostics.covarianceDiagnostic(first.layer,mismatch,'Q','C');}catch(e){rejectedBinding=true;}
assert(rejectedBinding,'mismatched dataset rejected');
for(const options of [{h:0},{h:true},{h:1.5},{h:'5'},{omission:1}]) {
  let rejected=false;try{valpasDiagnostics.covarianceDiagnostic(first.layer,first.dataset,'Q','C',options);}catch(e){rejected=true;}
  assert(rejected,'invalid options rejected');
}
""", cases)

    def test_metadata_controls_omission_safe_hovers_and_saved_rank_invariance(self):
        layer = profile_layer()
        # Distinct display order; every required ID remains present.
        layer['observation_ids'].reverse()
        for f in layer['features']:
            f['values'].reverse(); f['observed'].reverse()
        hostile = '</script><script>globalThis.b1Pwned=true</script>\u2028Ω'
        layer['features'][0]['label'] = hostile
        result = profiled_result(layer)
        doc = {'schema_version': 1, 'dataset': copy.deepcopy(layer['dataset']),
               'fields': {'condition': 'categorical', 'age': 'continuous', hostile: 'categorical'},
               'records': [{'observation_id': sid, 'values': {'condition': group, 'age': age, hostile: hostile}}
                           for sid, group, age in [('S01', 'Z', 60), ('S02', 'A', 50), ('S03', 'B', 40),
                                                   ('S04', None, 30), ('S05', '', 20)]]}
        metadata = SampleMetadata.from_dict(doc)
        report, payload = report_with_payload(result, lambda p: p.update(sample_metadata=metadata.to_dict()))
        selected_layer = payload['layers'][0]
        ds = payload['dataset']
        expected = {'covariance': covariance_diagnostic(selected_layer, ds, 'M01', 'P01', h=1, omission=True),
                    'groups': [group_summary(selected_layer, ds, metadata, ds[role+'_namespace'], fid, 'condition')
                               for role, fid in [('query', 'M01'), ('candidate', 'P01')]]}
        self.chrome(report, r"""
assert(!window.b1Pwned,'hostile data executed');
// There must be no diagnostics before selecting an embedded pair.
assert(!document.querySelector('.covariance-diagnostics'),'no eager UI pair calculations');
const payload=JSON.parse(document.getElementById('comparison-data').textContent);
const baseline=JSON.stringify({ranks:payload.details.M01.ranks,summaries:payload.summaries,agreement:payload.agreement});
const overview=section('2').innerHTML;
const workspace=selectPair();
const rankMarkup=[...workspace.querySelectorAll('table')].filter(t=>!t.closest('.profile-layer')).map(t=>t.innerHTML).join('');
assert(document.querySelector('.diagnostic-h').value==='5','default h');
assert(exact('.diagnostic-exact').remaining.reason==='not_requested','omission opt-in');
const color=document.querySelector('.metadata-color'),group=document.querySelector('.metadata-group'),order=document.querySelector('.sample-order');
const option=(select,label)=>[...select.options].find(o=>o.textContent===label||o.textContent.startsWith(label+' (')).value;
assert(order.value==='dataset','explicit dataset default');
const positions=()=>Object.fromEntries([...document.querySelectorAll('[data-profile-role="query"]')].map(n=>[n.dataset.observationId,Number(n.getAttribute('cx'))]));
const originalPositions=positions();assert(originalPositions.S01===60&&originalPositions.S06===670,'dataset not reversed layer order');
change(color,option(color,'condition'));
assert(document.querySelector('.metadata-legend').textContent.includes('Missing metadata'),'categorical missing legend');
assert(document.querySelectorAll('circle.metadata-missing').length>0,'missing style');
assert(document.querySelectorAll('circle.imputed').length===2,'original masks retained');
change(group,option(group,'condition'));
[...document.querySelectorAll('.group-exact pre')].forEach((node,i)=>compare(JSON.parse(node.textContent),inputs.groups[i],'UI group '+i));
assert(document.querySelector('.group-summaries').textContent.includes('Missing group excluded: 2'),'missing group count');
const groupsBefore=document.querySelector('.group-summaries').textContent;
change(color,option(color,'age'));
assert(document.querySelector('.metadata-legend').textContent.includes('20 (blue) → 60 (red)'),'continuous legend');
assert(document.querySelector('.group-summaries').textContent===groupsBefore,'color does not choose grouping');
change(order,'metadata');assert(positions().S01>positions().S04,'continuous ascending order');
change(order,'id');assert(JSON.stringify(positions())===JSON.stringify(originalPositions),'ID ascending order');
change(order,'dataset');assert(JSON.stringify(positions())===JSON.stringify(originalPositions),'restore explicit order');
const h=document.querySelector('.diagnostic-h');change(h,'1');
assert(exact('.diagnostic-exact').remaining.reason==='not_requested','h not implicit omission');
document.querySelector('.omission-preview').click();compare(exact('.diagnostic-exact'),inputs.covariance,'UI omission');
compare(exact('.diagnostic-exact').remaining.mean_x,7/3,'recentered remaining mean');
change(h,'2');assert(exact('.diagnostic-exact').remaining.reason==='not_requested','changing h clears preview');
change(h,'0');assert(document.querySelector('.omission-preview').disabled,'invalid h blocked');change(h,'1');
const fraction=document.querySelector('.group-fraction');fraction.checked=false;fraction.dispatchEvent(new Event('change'));
assert([...document.querySelectorAll('.group-exact pre')].every(n=>JSON.parse(n.textContent).fraction_status==='not_requested'),'optional fraction');
assert([...workspace.querySelectorAll('svg title')].some(n=>n.textContent.includes('S06')&&n.textContent.includes('age=missing')),'missing record hover');
assert([...workspace.querySelectorAll('svg title')].some(n=>n.textContent.includes('S01')&&n.textContent.includes('</script>')),'safe hostile metadata hover');
assert(!window.b1Pwned,'hostile text stayed inert');
assert(section('2').innerHTML===overview,'overview untouched');
assert([...workspace.querySelectorAll('table')].filter(t=>!t.closest('.profile-layer')).map(t=>t.innerHTML).join('')===rankMarkup,'rank DOM unchanged');
const after=JSON.parse(document.getElementById('comparison-data').textContent);
assert(JSON.stringify({ranks:after.details.M01.ranks,summaries:after.summaries,agreement:after.agreement})===baseline,'saved payload unchanged');
assert(!document.querySelector('script[src],link[href],img,iframe'),'no external resources');
""", expected)

    def test_old_payload_missing_metadata_and_unavailable_profiles_no_fallback(self):
        cases = [('old metadata key absent', profiled_result(), 'Sample metadata unavailable', None),
                 ('null metadata', profiled_result(), 'Sample metadata unavailable', None),
                 ('no profiles', fixture_result(), 'No profile layers embedded', None)]
        for reason in ('missing_feature', 'missing_required_observations', 'original_mask_unavailable'):
            layer = profile_layer()
            if reason == 'missing_feature':
                layer['features'] = [f for f in layer['features'] if f['feature_id'] != 'P01']
            elif reason == 'missing_required_observations':
                layer['observation_ids'].pop()
                for f in layer['features']:
                    f['values'].pop(); f['observed'].pop()
            else:
                layer['mask_source'] = 'unavailable'
                for f in layer['features']:
                    f['observed'] = None
            cases.append((reason, profiled_result(layer), reason, reason))
        for name, result, message, reason in cases:
            with self.subTest(name=name):
                def mutate(payload):
                    if name == 'old metadata key absent':
                        payload.pop('sample_metadata', None)
                    else:
                        payload['sample_metadata'] = None
                report, _ = report_with_payload(result, mutate)
                self.chrome(report, r"""
const workspace=selectPair();assert(workspace.textContent.includes(inputs.message),'absence reason');
if(inputs.reason){
  const result=exact('.diagnostic-exact');assert(result.reason===inputs.reason,'diagnostic exact reason');
  assert(result.products.length===0&&result.joint_observed_count===null,'no fallback cohort');
  assert(workspace.querySelectorAll('svg').length===0,'no fallback plots');
} else if(document.querySelector('.metadata-color')) {
  assert(document.querySelector('.metadata-color').disabled,'no metadata color fallback');
  assert(document.querySelector('.metadata-group').disabled,'no metadata group fallback');
  assert(exact('.diagnostic-exact').status==='available','covariance does not require metadata');
}
""", {'message': message, 'reason': reason})

    def test_diagnostics_only_called_for_selected_pair_not_preexported_rows(self):
        report, _ = report_with_payload(profiled_result())
        # Wrap the narrow API AFTER its definition but BEFORE dashboard startup.
        boundary = "})();\n(() => {\n  'use strict';\n  const data ="
        replacement = """})();
window.b1Calls=[];
const realDiagnostics=window.valpasDiagnostics;
window.valpasDiagnostics={...realDiagnostics,covarianceDiagnostic:(...args)=>{
  window.b1Calls.push([args[2],args[3]]);return realDiagnostics.covarianceDiagnostic(...args);
}};
(() => {
  'use strict';
  const data ="""
        self.assertIn(boundary, report)
        report = report.replace(boundary, replacement, 1)
        self.chrome(report, r"""
assert(window.b1Calls.length===0,'no overview all-pair diagnostics');
selectPair();assert(JSON.stringify(window.b1Calls)==='[["M01","P01"]]','only selected pair');
change(document.querySelector('.sample-order'),'id');assert(window.b1Calls.length===1,'order does not recalculate diagnostics');
change(document.querySelector('.diagnostic-h'),'1');
assert(window.b1Calls.length===2&&window.b1Calls.every(p=>p[0]==='M01'&&p[1]==='P01'),'on-demand selected pair only');
""")


if __name__ == '__main__':
    unittest.main()
