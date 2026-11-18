/* Packaged vanilla JS: presentation only. Metrics and denominators come from Python. */
(() => {
  'use strict';
  const data = JSON.parse(document.getElementById('comparison-data').textContent);
  const app = document.getElementById('app');
  app.replaceChildren();
  const state = {depth: Math.min(10, data.report_settings.max_interactive_depth), query: null, candidate: null, pair: null, search: '', candidateSearch: '', hidden: new Set(), pins: new Set(data.report_settings.pinned_candidate_ids)};
  const text = value => value === null || value === undefined ? 'unavailable / not applicable' : typeof value === 'object' ? JSON.stringify(value) : String(value);
  function el(tag, content, parent, cls) {
    const n = document.createElement(tag);
    if (content !== null && content !== undefined) n.textContent = text(content);
    if (cls) n.className = cls;
    if (parent) parent.append(n);
    return n;
  }
  function button(label, parent, action) {const b = el('button', label, parent); b.type = 'button'; b.addEventListener('click', action); return b;}
  function section(title) {const n = el('section', null, app); el('h2', title, n); return n;}
  function detail(title, value, parent) {const d = el('details', null, parent); el('summary', title, d); el('pre', JSON.stringify(value, null, 2), d); return d;}
  function table(rows, parent, onSelect, columns) {
    if (!rows.length) {el('p', 'No matching embedded rows. Unavailable is not zero.', parent); return;}
    const wrap = el('div', null, parent, 'scroll'), t = el('table', null, wrap);
    const head = el('tr', null, el('thead', null, t)), body = el('tbody', null, t);
    columns = columns || Object.keys(rows[0]);
    let displayed = rows.slice(), ascending = true;
    function paint() {body.replaceChildren(); displayed.forEach(row => {const tr = el('tr', null, body, onSelect ? 'selectable' : ''); columns.forEach(k => el('td', row[k], tr)); if (onSelect) {tr.tabIndex = 0; tr.addEventListener('click', () => onSelect(row)); tr.addEventListener('keydown', e => {if(e.key === 'Enter') onSelect(row);});}});}
    columns.forEach(k => button(k, el('th', null, head), () => {displayed.sort((a,b) => {const x = a[k], y = b[k]; return (x === y ? 0 : x === null ? 1 : y === null ? -1 : x < y ? -1 : 1) * (ascending ? 1 : -1);}); ascending = !ascending; paint();}));
    paint();
  }
  const nsEqual = (a,b) => a.id === b.id && a.modality === b.modality;
  function features(id, ns) {return data.layers.flatMap(l => l.features.filter(f => f.feature_id === id && nsEqual(f.namespace, ns)));}
  function searchable(id, ns) {return [id, ns.id, ns.modality, ...features(id,ns).flatMap(f => [f.label || '', f.annotations || ''])].join(' ').toLowerCase();}
  function label(id, ns) {const names = [...new Set(features(id, ns).map(f => f.label).filter(Boolean))]; return names.length ? `${names.join(' / ')} [${id}; ${ns.modality}]` : `${id} [${ns.modality}]`;}
  const qns = data.dataset.query_namespace, cns = data.dataset.candidate_namespace;
  const identity = section('1 · Dataset, outputs and comparability');
  el('p', data.comparison_id, identity, 'muted');
  el('p', data.sensitive_data_warning, identity, 'notice');
  data.omissions.forEach(o => el('p', o, identity, 'notice'));
  table(data.summaries.dataset_summary, identity);
  detail('Dataset identity and cohort', data.dataset, identity);
  detail('Analysis settings (fixed scientific pools)', data.analysis_settings, identity);
  detail('Output / method / configuration / run inventory', data.summaries.outputs, identity);
  detail('Configuration differences', data.summaries.configuration_differences, identity);
  detail('Compatibility warnings', data.warnings, identity);
  const controls = el('div', null, app, 'controls');
  const dl = el('label', 'Interactive depth ', controls), depth = el('input', null, dl);
  depth.type = 'number'; depth.min = '1'; depth.max = String(data.report_settings.max_interactive_depth); depth.value = state.depth; depth.id = 'depth';
  depth.addEventListener('change', () => {const v = Number(depth.value); if(Number.isInteger(v) && v >= 1 && v <= data.report_settings.max_interactive_depth) {state.depth = v; renderOverview(); renderQueries(); renderWorkspace();}});
  el('p', `Details: ${data.query_ids.length}/${data.all_query_ids.length} queries; maximum interactive depth ${data.report_settings.max_interactive_depth}. Whole-cohort summaries and full saved tables are independent of this scope. Filters/hidden outputs never change pools or denominators.`, controls);
  const visibility = el('details', null, controls); el('summary', 'Display outputs (does not redefine analysis)', visibility);
  data.summaries.outputs.forEach(o => {const l = el('label', `${o.label} [${o.output_id}; ${o.method_id}/${o.configuration_id}/${o.run_id}] `, visibility), c = el('input', null, l); c.type='checkbox'; c.checked=true; c.addEventListener('change', () => {if(c.checked) state.hidden.delete(o.output_id); else state.hidden.add(o.output_id); renderOverview(); renderWorkspace();});});
  const overview = section('2 · Whole-cohort output-pair agreement');
  const recurrence = section('3 · Run recurrence — separate from method agreement');
  const queries = section('4 · Query browser');
  const searchLabel = el('label', 'Search canonical ID, label, modality or available annotation ', queries), search = el('input', null, searchLabel); search.type='search'; search.id='query-search';
  search.addEventListener('input', () => {state.search=search.value.toLowerCase(); renderQueries();});
  button('Clear chart selection', queries, () => {state.pair=null; renderQueries();});
  const queryRows = el('div', null, queries);
  const workspace = section('5 · Query → candidates → measured profiles');
  const visiblePair = r => !state.hidden.has(r.left_output_id) && !state.hidden.has(r.right_output_id);
  function selectPair(row) {state.pair=[row.left_output_id,row.right_output_id]; renderQueries(); queries.scrollIntoView({block:'start'});}
  function renderOverview() {
    overview.replaceChildren(); el('h2', '2 · Whole-cohort output-pair agreement', overview);
    el('p', 'Heatmap tiles show median controlled overlap and evaluable / declared queries. Select a tile to inspect its query-level values. Gray means unavailable, not zero. Outputs and runs are never collapsed.', overview);
    const heat = el('div', null, overview, 'heat');
    const rows = data.summaries.agreement_summary.filter(r => r.requested_depth === state.depth && visiblePair(r));
    rows.forEach(r => {const b=button(`${r.left_output_id} × ${r.right_output_id}\n${r.pair_class}\nmedian ${text(r.median)} · ${r.evaluable_queries}/${r.declared_queries} evaluable\n${r.status}`, heat, () => selectPair(r)); b.style.backgroundColor = r.median === null ? '#e3e7ea' : `hsl(202 65% ${94-r.median*39}%)`; b.title=JSON.stringify(r);});
    el('h3', 'Agreement across depth', overview);
    el('p', 'Each line is one output pair; points show saved cohort medians, with denominators on hover. Select a point to set depth and drill down.', overview);
    const svg = makeSvg(720,240,overview,'Cohort median controlled overlap versus depth');
    axis(svg, 'Requested depth →', 'Median overlap (0–1)');
    rows.forEach((pair, index) => {
      const series = data.summaries.agreement_summary.filter(r => r.left_output_id===pair.left_output_id && r.right_output_id===pair.right_output_id && r.requested_depth<=data.report_settings.max_interactive_depth && r.median!==null);
      const color = `hsl(${index*83%360} 65% 35%)`;
      let prior=null;
      series.forEach(r => {const x=55+(r.requested_depth-1)*610/Math.max(1,data.report_settings.max_interactive_depth-1), y=200-r.median*155; if(prior) shape('line',{x1:prior[0],y1:prior[1],x2:x,y2:y,stroke:color},svg); const dot=shape('circle',{cx:x,cy:y,r:4,fill:color,tabindex:0,role:'button'},svg); title(dot,`${r.left_output_id} × ${r.right_output_id}; depth ${r.requested_depth}; median ${r.median}; evaluable ${r.evaluable_queries}/${r.declared_queries}`); const choose=()=>{state.depth=r.requested_depth; depth.value=state.depth; selectPair(r); renderOverview(); renderWorkspace();}; dot.addEventListener('click',choose); dot.addEventListener('keydown',e=>{if(e.key==='Enter')choose();}); prior=[x,y];});
    });
    detail('Exact agreement summaries, denominators and exclusion reasons', rows, overview);
    detail('Per-query/output coverage and comparability (whole cohort)', data.coverage, overview);
    recurrence.replaceChildren(); el('h2','3 · Run recurrence — separate from method agreement',recurrence);
    el('p','Expected runs remain the denominator, including unavailable runs. A single run is not assessed. Select a group/query to inspect candidate nominations.',recurrence);
    table(data.run_groups.filter(r=>r.requested_depth===state.depth),recurrence,r=>selectQuery(r.query_id));
  }
  function renderQueries() {
    queryRows.replaceChildren();
    const pairRows = state.pair ? data.agreement.filter(r=>r.requested_depth===state.depth && r.left_output_id===state.pair[0] && r.right_output_id===state.pair[1]) : null;
    if(state.pair) el('p',`Selected output pair: ${state.pair.join(' × ')}`,queryRows,'notice');
    const rows=data.summaries.query_summary.filter(r=>r.requested_depth===state.depth && searchable(r.query_id,qns).includes(state.search)).map(r=>{const p=pairRows && pairRows.find(v=>v.query_id===r.query_id); return {query_id:r.query_id,display:label(r.query_id,qns),detail_scope:data.query_ids.includes(r.query_id)?'embedded':'outside embedded detail scope',...r,...(state.pair?{pair_overlap:p?p.overlap_fraction:null,pair_status:p?p.status:'excluded',pair_reason:p?p.reason:r.reason}: {})};});
    el('p',`${rows.length} matching queries. Select any row; click column headings to sort. Search covers only embedded labels/annotations. A missing match is not evidence of absence; re-export with explicit query IDs or pinned candidate IDs.`,queryRows);
    table(rows,queryRows,r=>selectQuery(r.query_id));
  }
  function selectQuery(q) {state.query=q; state.candidate=null; state.candidateSearch=''; renderWorkspace(); workspace.scrollIntoView({block:'start'});}
  function renderWorkspace() {
    workspace.replaceChildren(); el('h2','5 · Query → candidates → measured profiles',workspace);
    if(!state.query) {el('p','Start with the overview, or select a query above. No target query is required to export or explore this report.',workspace); return;}
    el('h3',label(state.query,qns),workspace);
    const d=data.details[state.query];
    if(!d) {el('p','This query is outside embedded detail scope. Full scientific tables retain its analysis rows. Re-export with this canonical query ID.',workspace,'notice');return;}
    detail('Query coverage, pools and comparability',d.coverage,workspace);
    detail('Agreement: requested/effective depths, lists and denominators',d.agreement.filter(r=>r.requested_depth===state.depth),workspace);
    detail('Top-list availability (all outputs, fixed pools)',d.tops.filter(r=>r.requested_depth===state.depth),workspace);
    const l=el('label','Find candidate by ID, label, modality or annotation ',workspace), input=el('input',null,l); input.type='search'; input.id='candidate-search'; input.value=state.candidateSearch;
    const list=el('div',null,workspace), profile=el('div',null,workspace);
    function candidates() {
      list.replaceChildren();
      const union=new Set(state.pins);
      d.tops.filter(r=>r.requested_depth===state.depth).forEach(r=>(r.candidate_ids||[]).forEach(c=>union.add(c)));
      const needle=state.candidateSearch.toLowerCase();
      const ids=d.candidate_ids.filter(c=>needle?searchable(c,cns).includes(needle):union.has(c));
      el('p',`${ids.length} candidates shown; ${d.candidate_ids.length} embedded. Default order: canonical ID, not consensus rank. Search can reveal candidates embedded at other depths. No match: outside scope or absent; re-export pinned IDs. Hidden outputs do not change this union.`,list);
      const rows=ids.map(c=>({candidate_id:c,display:label(c,cns),pinned:state.pins.has(c)}));
      table(rows,list,r=>{state.candidate=r.candidate_id; showCandidate();});
    }
    input.addEventListener('input',()=>{state.candidateSearch=input.value;candidates();});
    function showCandidate() {
      profile.replaceChildren(); if(!state.candidate)return;
      const c=state.candidate; el('h3',label(c,cns),profile);
      button(state.pins.has(c)?'Unpin candidate':'Pin candidate in this view',profile,()=>{if(state.pins.has(c))state.pins.delete(c);else state.pins.add(c);candidates();showCandidate();});
      el('p','Signed scores retain native output semantics; do not compare score magnitudes across methods. Missing ranks are not zero.',profile);
      table(d.ranks.filter(r=>r.candidate_id===c&&!state.hidden.has(r.output_id)),profile);
      detail('Sparse absent-record statuses (not fabricated ranks)',d.omissions.filter(r=>r.candidate_id===c),profile);
      detail('Candidate run recurrence and expected/evaluable runs',d.recurrence.filter(r=>r.candidate_id===c&&r.requested_depth===state.depth),profile);
      if(!data.layers.length)el('p','No profile layers embedded (not supplied or explicitly omitted). Rankings remain usable; profile evidence is unavailable.',profile,'notice');
      data.layers.forEach(layer=>renderProfile(layer,d,c,profile));
    }
    candidates(); showCandidate();
  }
  function makeSvg(w,h,parent,description){const s=shape('svg',{viewBox:`0 0 ${w} ${h}`,width:w,height:h,role:'img','aria-label':description},parent);title(s,description);return s;}
  function shape(tag,attrs,parent){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));parent.append(n);return n;}
  function title(n,s){const t=shape('title',{},n);t.textContent=s;}
  function svgText(s,x,y,t){const n=shape('text',{x,y},s);n.textContent=t;}
  function axis(s,xlabel,ylabel){shape('path',{d:'M50 35 V200 H680',fill:'none',stroke:'#789'},s);svgText(s,55,20,ylabel);svgText(s,280,230,xlabel);}
  function scale(values,low,high){let min=Infinity,max=-Infinity;values.forEach(v=>{min=Math.min(min,v);max=Math.max(max,v);});return v=>max===min?(low+high)/2:low+(v-min)*(high-low)/(max-min);}
  function renderProfile(layer,d,c,parent){
    const box=el('section',null,parent);el('h3',`Measurement layer: ${layer.layer_id}`,box);
    el('p',`Units: ${layer.units}; transform: ${layer.transform}; mask: ${layer.mask_source}; provenance: ${layer.provenance}`,box);
    detail('Relationship to algorithm layers (not attribution)',layer.algorithm_layers,box);
    const coverage=data.feature_coverage.filter(r=>r.layer_id===layer.layer_id&&((r.feature_id===state.query&&nsEqual(r.namespace,qns))||(r.feature_id===c&&nsEqual(r.namespace,cns))));table(coverage,box);
    const p=d.profiles.find(r=>r.layer_id===layer.layer_id&&r.candidate_id===c);
    if(!p||p.reason&&p.reason!=='no_jointly_observed_finite_values'){el('p',`Plots unavailable: ${p?p.reason:'no profile metadata'}. No silent feature/cohort subsetting.`,box,'notice');return;}
    const q=layer.features.find(f=>f.feature_id===state.query&&nsEqual(f.namespace,qns)), f=layer.features.find(f=>f.feature_id===c&&nsEqual(f.namespace,cns));
    el('p',`Jointly observed finite points: ${p.joint_observed_count}. Filled blue: query observed; filled purple: candidate observed. Hollow orange: finite originally unobserved/imputed; excluded from scatter and observed-only summaries. Constant/near-empty flags appear above. Hover points for exact sample IDs and values.`,box);
    if(p.joint_indices.length){const s=makeSvg(720,240,box,'Jointly observed scatter');axis(s,`${c} (${layer.units})`,`${state.query} (${layer.units})`);const xs=scale(p.joint_indices.map(i=>f.values[i]),60,670),ys=scale(p.joint_indices.map(i=>q.values[i]),195,40);p.joint_indices.forEach(i=>{const n=shape('circle',{cx:xs(f.values[i]),cy:ys(q.values[i]),r:4,class:'observed'},s);title(n,`${layer.observation_ids[i]}: query=${q.values[i]}, candidate=${f.values[i]}`);});}else el('p',p.reason,box,'notice');
    const s=makeSvg(720,240,box,'Sample-level observed and imputed profiles');axis(s,'Required observation order →',`Values (${layer.units}); shared scale`);
    const all=[...p.query_indices,...p.query_unobserved_indices].map(i=>q.values[i]).concat([...p.candidate_indices,...p.candidate_unobserved_indices].map(i=>f.values[i]));
    if(!all.length)return;
    const ys=scale(all,195,40), order=data.dataset.observation_ids;
    [['query',q,'observed'],['candidate',f,'candidate']].forEach(([role,feature,cls])=>{[false,true].forEach(imputed=>{p[role+(imputed?'_unobserved_indices':'_indices')].forEach(i=>{const x=60+order.indexOf(layer.observation_ids[i])*610/Math.max(1,order.length-1);const n=shape('circle',{cx:x,cy:ys(feature.values[i]),r:imputed?5:3.5,class:imputed?'imputed':cls},s);title(n,`${layer.observation_ids[i]}: ${feature.feature_id}=${feature.values[i]}; ${imputed?'originally unobserved / imputed':'observed'}`);});});});
  }
  renderOverview();renderQueries();renderWorkspace();
  document.documentElement.dataset.reportReady='true';
})();
