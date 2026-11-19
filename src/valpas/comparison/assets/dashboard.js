/* Saved association metrics stay in Python. Only selected observed-data B1
 * descriptions are calculated here, mirroring diagnostics.py on validated data.
 * No scoring, attribution, refitting or all-pair diagnostic cache. */
window.valpasDiagnostics = (() => {
  'use strict';
  // Python string order is Unicode code-point order, not locale or UTF-16 order.
  function idOrder(a, b) {
    const x = Array.from(a, c => c.codePointAt(0)), y = Array.from(b, c => c.codePointAt(0));
    for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i];
    return x.length - y.length;
  }
  function checked(v) {if (!Number.isFinite(v)) throw new RangeError('numeric_range'); return v;}
  // Error-free partial summation, including final half-even rounding, as in
  // math.fsum. Intermediate overflow is unavailable even after cancellation.
  function fsum(values) {
    const partials = [];
    for (let x of values) {
      let i = 0;
      for (let y of partials) {
        if (Math.abs(x) < Math.abs(y)) [x, y] = [y, x];
        const hi = checked(x + y), lo = y - (hi - x);
        if (lo) partials[i++] = lo;
        x = hi;
      }
      partials.length = i;
      if (x) partials.push(x);
    }
    let n = partials.length, hi = 0, lo = 0;
    if (n) {
      hi = partials[--n];
      while (n) {
        const x = hi, y = partials[--n];
        hi = x + y; lo = y - (hi - x);
        if (lo) break;
      }
      if (n && ((lo < 0 && partials[n-1] < 0) || (lo > 0 && partials[n-1] > 0))) {
        const y = lo * 2, x = hi + y;
        if (y === x - hi) hi = x;
      }
    }
    return checked(hi);
  }
  const mean = values => fsum(values.map(v => v / values.length));
  const nsEqual = (a, b) => a.id === b.id && a.modality === b.modality;
  const feature = (layer, ns, fid) => layer.features.find(f => f.feature_id === fid && nsEqual(f.namespace, ns));
  const mask = (layer, f) => layer.mask_source === 'raw_finite' ? f.values.map(v => v !== null) : layer.mask_source === 'unavailable' ? null : f.observed;
  function coverageReason(layer, dataset, f) {
    const available = new Set(layer.observation_ids);
    return !f ? 'missing_feature' : dataset.observation_ids.some(s => !available.has(s)) ? 'missing_required_observations' : layer.mask_source === 'unavailable' ? 'original_mask_unavailable' : null;
  }
  const extras = (ids, required) => ids.filter(s => !required.has(s)).sort(idOrder);
  function same(a, b) {
    if (a === b) return true;
    if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false;
    const keys = Object.keys(a);
    return keys.length === Object.keys(b).length && keys.every(k => Object.hasOwn(b, k) && same(a[k], b[k]));
  }
  function binding(bound, dataset) {
    for (const k of Object.keys(dataset)) {
      const a = dataset[k], b = bound[k];
      let equal = a != null && b != null;
      if (equal) {
        if (k === 'observation_ids') equal = same([...a].sort(idOrder), [...b].sort(idOrder));
        else if (k === 'dataset_evidence') equal = a.source === b.source && (!(a.type === 'fingerprint' && b.type === 'fingerprint') || a.value === b.value);
        else equal = same(a,b);
      }
      if (!equal) throw new TypeError('dataset binding must explicitly match: ' + k);
    }
  }
  function layerBinding(layer, dataset) {
    binding(layer.dataset, dataset);
    if (!layer.subset_extra_observations && extras(layer.observation_ids, new Set(dataset.observation_ids)).length) throw new TypeError('extra profile observations require explicit subsetting');
  }
  function requireText(value) {if (typeof value !== 'string' || !value.length) throw new TypeError('expected nonempty string');}
  function emptyStats(count, reason) {
    return {count, mean_x:null, mean_y:null, covariance:null, correlation:null,
      status:'unavailable', reason, covariance_status:'unavailable', covariance_reason:reason,
      correlation_status:'unavailable', correlation_reason:reason};
  }
  function stats(xs, ys) {
    const row = emptyStats(xs.length, 'insufficient_observations');
    if (xs.length < 3) return row;
    let dx, dy;
    try {
      const mx = mean(xs), my = mean(ys);
      dx = xs.map(x => checked(x - mx)); dy = ys.map(y => checked(y - my));
      const products = dx.map((x,i) => checked(x * dy[i]));
      const covariance = fsum(products.map(p => p / (xs.length - 1)));
      Object.assign(row, {mean_x:mx, mean_y:my, covariance, status:'available', reason:null, covariance_status:'available', covariance_reason:null});
    } catch (e) {if (!(e instanceof RangeError)) throw e; return emptyStats(xs.length, 'numeric_range');}
    try {
      const sx = dx.reduce((m,v) => Math.max(m, Math.abs(v)), 0), sy = dy.reduce((m,v) => Math.max(m, Math.abs(v)), 0);
      if (sx === 0 || sy === 0) row.correlation_reason = 'zero_variance';
      else {
        const ux = dx.map(v => v / sx), uy = dy.map(v => v / sy);
        const corr = checked(fsum(ux.map((x,i) => x * uy[i])) / (Math.sqrt(fsum(ux.map(x => x*x))) * Math.sqrt(fsum(uy.map(y => y*y)))));
        Object.assign(row, {correlation:Math.max(-1, Math.min(1, corr)), correlation_status:'available', correlation_reason:null});
      }
    } catch (e) {if (!(e instanceof RangeError)) throw e; row.correlation_reason = 'numeric_range';}
    return row;
  }
  function covarianceDiagnostic(layer, dataset, query_id, candidate_id, {h=5, omission=false}={}) {
    requireText(query_id); requireText(candidate_id);
    if (!Number.isInteger(h) || h < 1 || typeof omission !== 'boolean') throw new TypeError('expected positive integer h and boolean omission');
    layerBinding(layer, dataset);
    const required = [...dataset.observation_ids], requiredSet = new Set(required);
    const q = feature(layer, dataset.query_namespace, query_id), c = feature(layer, dataset.candidate_namespace, candidate_id);
    let reason = coverageReason(layer, dataset, q) || coverageReason(layer, dataset, c);
    const indices = new Map(layer.observation_ids.map((sid,i) => [sid,i]));
    let joint = [], count = null;
    if (!reason) {
      const qm = mask(layer,q), cm = mask(layer,c);
      joint = required.filter(sid => {const i = indices.get(sid); return qm[i] && cm[i] && q.values[i] !== null && c.values[i] !== null;});
      count = joint.length;
      if (!count) reason = 'no_jointly_observed_finite_values';
    }
    const jointSet = new Set(joint);
    const row = {layer_id:layer.layer_id, query_id, candidate_id, h, omission, required_observation_ids:required,
      joint_observed_count:count, joint_observation_ids:joint, excluded_observation_ids:required.filter(s => !jointSet.has(s)),
      excluded_profile_observation_ids:extras(layer.observation_ids, requiredSet), mask_source:layer.mask_source,
      status:'unavailable', reason, products:[], absolute_product_sum:null, selected_observation_ids:[], effective_h:0, largest_h_share:null,
      original:emptyStats(count, reason), remaining:emptyStats(null, omission ? reason : 'not_requested'),
      omitted_observation_ids:[], retained_observation_ids:[...joint]};
    if (reason) return row;
    const xs = joint.map(s => q.values[indices.get(s)]), ys = joint.map(s => c.values[indices.get(s)]);
    row.original = stats(xs,ys);
    if (joint.length < 3) row.reason = 'insufficient_joint_observations';
    else {
      try {
        const mx = mean(xs), my = mean(ys);
        const products = xs.map((x,i) => checked(checked(x - mx) * checked(ys[i] - my)));
        const denominator = fsum(products.map(Math.abs));
        row.products = joint.map((sid,i) => ({observation_id:sid, product:products[i], absolute_share:denominator ? checked(Math.abs(products[i]) / denominator) : null}));
        row.absolute_product_sum = denominator;
        if (denominator === 0) row.reason = 'zero_absolute_product_sum';
        else {
          const selected = joint.map((s,i) => i).sort((a,b) => Math.abs(products[b]) - Math.abs(products[a]) || idOrder(joint[a],joint[b])).slice(0,h);
          const share = fsum(selected.map(i => Math.abs(products[i]) / denominator));
          Object.assign(row, {status:'available', reason:null, effective_h:selected.length, selected_observation_ids:selected.map(i => joint[i]), largest_h_share:share});
        }
      } catch (e) {if (!(e instanceof RangeError)) throw e; Object.assign(row, {reason:'numeric_range', products:[], absolute_product_sum:null});}
    }
    if (omission) {
      if (row.status === 'available') {
        const omitted = new Set(row.selected_observation_ids), retained = joint.map((s,i) => i).filter(i => !omitted.has(joint[i]));
        Object.assign(row, {omitted_observation_ids:[...row.selected_observation_ids], retained_observation_ids:retained.map(i => joint[i]), remaining:stats(retained.map(i => xs[i]), retained.map(i => ys[i]))});
      } else row.remaining = emptyStats(joint.length, row.reason);
    }
    return row;
  }
  function groupSummary(layer, dataset, metadata, namespace, feature_id, field, {include_fraction=true}={}) {
    requireText(feature_id); requireText(field);
    if (typeof include_fraction !== 'boolean') throw new TypeError('expected boolean include_fraction');
    layerBinding(layer, dataset); binding(metadata.dataset, dataset);
    const required = [...dataset.observation_ids], requiredSet = new Set(required);
    const records = new Map(metadata.records.map(r => [r.observation_id, r.values]));
    if (!metadata.subset_extra_observations && extras([...records.keys()], requiredSet).length) throw new TypeError('extra metadata observations require explicit subsetting');
    const value = sid => {const r = records.get(sid); return r && Object.hasOwn(r,field) ? r[field] : null;};
    const f = feature(layer, namespace, feature_id), fieldType = Object.hasOwn(metadata.fields,field) ? metadata.fields[field] : null;
    const reason = fieldType === null ? 'missing_group_field' : fieldType !== 'categorical' ? 'categorical_field_required' : coverageReason(layer, dataset, f);
    const row = {layer_id:layer.layer_id, namespace:{...namespace}, feature_id, field, field_type:fieldType, include_fraction,
      required_count:required.length, required_observation_ids:required, known_group_count:null, known_group_observation_ids:[],
      observed_finite_count:null, observed_finite_observation_ids:[], included_count:null, included_observation_ids:[], groups:[],
      exclusions:{missing_group:{count:null, observation_ids:[]}, not_observed_finite:{count:null, observation_ids:[]}},
      excluded_profile_observation_ids:extras(layer.observation_ids, requiredSet), excluded_metadata_observation_ids:extras([...records.keys()], requiredSet),
      mask_source:layer.mask_source, status:'unavailable', reason, between_group_ss:null, total_ss:null, between_group_fraction:null,
      fraction_status:include_fraction ? 'unavailable' : 'not_requested', fraction_reason:include_fraction ? reason : 'not_requested'};
    if (reason) return row;
    const observedMask = mask(layer,f), indices = new Map(layer.observation_ids.map((sid,i) => [sid,i]));
    const known = required.filter(s => value(s) !== null), observed = required.filter(s => observedMask[indices.get(s)] && f.values[indices.get(s)] !== null);
    const knownSet = new Set(known), observedSet = new Set(observed), included = known.filter(s => observedSet.has(s));
    const missing = required.filter(s => !knownSet.has(s)), notObserved = known.filter(s => !observedSet.has(s));
    Object.assign(row, {known_group_count:known.length, known_group_observation_ids:known, observed_finite_count:observed.length, observed_finite_observation_ids:observed,
      included_count:included.length, included_observation_ids:included,
      exclusions:{missing_group:{count:missing.length, observation_ids:missing}, not_observed_finite:{count:notObserved.length, observation_ids:notObserved}}});
    if (!included.length) {
      row.reason = 'no_known_group_observed_finite_values';
      if (include_fraction) row.fraction_reason = row.reason;
      return row;
    }
    const groups = new Map();
    included.forEach(s => {const g = value(s); if (!groups.has(g)) groups.set(g,[]); groups.get(g).push(f.values[indices.get(s)]);});
    row.groups = [...groups.keys()].sort(idOrder).map(g => ({group:g, count:groups.get(g).length, mean:null}));
    try {
      const means = row.groups.map(g => mean(groups.get(g.group)));
      row.groups.forEach((g,i) => {g.mean = means[i];});
    } catch (e) {if (!(e instanceof RangeError)) throw e; row.reason = 'numeric_range'; if (include_fraction) row.fraction_reason = 'numeric_range'; return row;}
    Object.assign(row, {status:'available', reason:null});
    if (include_fraction) {
      try {
        const values = included.map(s => f.values[indices.get(s)]), mx = mean(values);
        const total = fsum(values.map(v => checked((v - mx) ** 2)));
        const between = fsum(row.groups.map(g => checked(g.count * (g.mean - mx) ** 2)));
        const fraction = total ? checked(between / total) : null;
        Object.assign(row, {total_ss:total, between_group_ss:between, between_group_fraction:fraction,
          fraction_status:total ? 'available' : 'unavailable', fraction_reason:total ? null : 'zero_total_variation'});
      } catch (e) {if (!(e instanceof RangeError)) throw e; row.fraction_status = 'unavailable'; row.fraction_reason = 'numeric_range';}
    }
    return row;
  }
  return Object.freeze({covarianceDiagnostic, groupSummary});
})();
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
  function scale(values,low,high){let min=Infinity,max=-Infinity;values.forEach(v=>{min=Math.min(min,v);max=Math.max(max,v);});return v=>max===min?(low+high)/2:low+(Number.isFinite(max-min)?(v-min)/(max-min):(v/2-min/2)/(max/2-min/2))*(high-low);}
  // Display ordering is deliberately separate from all scientific cohort arrays.
  function codePointOrder(a,b) {
    const x=Array.from(a,c=>c.codePointAt(0)), y=Array.from(b,c=>c.codePointAt(0));
    for(let i=0;i<Math.min(x.length,y.length);i++)if(x[i]!==y[i])return x[i]-y[i];
    return x.length-y.length;
  }
  function renderProfile(layer,d,c,parent){
    const box=el('section',null,parent,'profile-layer');el('h3',`Measurement layer: ${layer.layer_id}`,box);
    el('p',`Units: ${layer.units}; transform: ${layer.transform}; mask: ${layer.mask_source}; provenance: ${layer.provenance}`,box);
    detail('Relationship to algorithm layers (not attribution)',layer.algorithm_layers,box);
    const coverage=data.feature_coverage.filter(r=>r.layer_id===layer.layer_id&&((r.feature_id===state.query&&nsEqual(r.namespace,qns))||(r.feature_id===c&&nsEqual(r.namespace,cns))));table(coverage,box);
    el('p','Observed-data descriptions only: not model attribution, causal effects, adjusted variance components or automatic confounding correction. No retraining, scoring, reranking or leave-one-out model evaluation. Display choices and omission previews never alter saved scores, ranks or agreement.',box,'notice');
    const metadata=data.sample_metadata || null, fields=metadata?Object.keys(metadata.fields).sort(codePointOrder):[];
    const records=new Map(metadata?metadata.records.map(r=>[r.observation_id,r.values]):[]);
    const metadataValue=(sid,field)=>{const r=records.get(sid);return r&&Object.hasOwn(r,field)?r[field]:null;};
    const hover=sid=>fields.length?fields.map(field=>`${field}=${metadataValue(sid,field)===null?'missing':text(metadataValue(sid,field))}`).join('; '):'sample metadata unavailable';
    const controls=el('div',null,box,'diagnostic-controls');
    function select(label,cls,options){const s=el('select',null,el('label',label+' ',controls),cls);options.forEach(([value,label])=>{const o=el('option',label,s);o.value=value;});return s;}
    // Index-valued options cannot collide with arbitrary metadata field names.
    const color=select('Color by','metadata-color',[['','Feature role'],...fields.map((f,i)=>[String(i),`${f} (${metadata.fields[f]})`])]);
    const order=select('Sample display order','sample-order',[['dataset','Dataset order (default)'],['id','Observation ID ascending'],['metadata','Selected color field ascending; missing last']]);
    const categorical=fields.filter(f=>metadata.fields[f]==='categorical');
    const group=select('Marginal grouping (separate from color)','metadata-group',[['','No grouping'],...categorical.map((f,i)=>[String(i),f])]);
    const fraction=el('input',null,el('label','Include between-group / total SS fraction ',controls),'group-fraction');fraction.type='checkbox';fraction.checked=true;
    if(!metadata||!fields.length){color.disabled=true;group.disabled=true;el('p',!metadata?'Sample metadata unavailable (not supplied, omitted, or older report). Group summaries and metadata coloring unavailable.':'No sample metadata fields declared. Group summaries and metadata coloring unavailable.',box,'notice');}
    else if(!categorical.length){group.disabled=true;el('p','No categorical metadata fields: group summaries unavailable; continuous fields are not automatically binned.',box,'notice');}
    const plots=el('div',null,box,'profile-plots'), groups=el('div',null,box,'group-summaries');
    const diagnostics=el('div',null,box,'covariance-diagnostics');
    el('h4','Joint-centered covariance contributions',diagnostics);
    const h=el('input',null,el('label','Largest absolute products h ',diagnostics),'diagnostic-h');h.type='number';h.min='1';h.step='1';h.value='5';
    let omission=false;
    const omit=button('Preview omission and recenter remaining pairs',diagnostics,()=>{omission=true;renderDiagnostic();});omit.className='omission-preview';
    button('Clear omission preview',diagnostics,()=>{omission=false;renderDiagnostic();});
    const diagnosticRows=el('div',null,diagnostics,'diagnostic-results');
    function renderDiagnostic(){
      if(!Number.isInteger(Number(h.value))||Number(h.value)<1)return;
      diagnosticRows.replaceChildren();
      const result=window.valpasDiagnostics.covarianceDiagnostic(layer,data.dataset,state.query,c,{h:Number(h.value),omission});
      el('p',`Status: ${result.status}; reason: ${text(result.reason)}. Joint observed: ${text(result.joint_observed_count)} / ${result.required_observation_ids.length}; excluded: ${result.excluded_observation_ids.length}. Selected: ${result.effective_h}; largest-h absolute-product share: ${text(result.largest_h_share)}.`,diagnosticRows,'diagnostic-status');
      el('p',`Signed products use joint-sample means. Sample covariance uses n−1. Omission preview: ${omission?'requested; retained pairs are recentered':'not requested'}.`,diagnosticRows);
      const selected=new Set(result.selected_observation_ids);
      table(result.products.map(r=>({...r,selected:selected.has(r.observation_id)})),diagnosticRows,null,['observation_id','product','absolute_share','selected']);
      table([{cohort:'original',...result.original},{cohort:'remaining (explicit omission)',...result.remaining}],diagnosticRows);
      detail('Exact covariance diagnostic, masks, exclusions and retained IDs',result,diagnosticRows).className='diagnostic-exact';
    }
    h.addEventListener('change',()=>{const n=Number(h.value);if(!Number.isInteger(n)||n<1){h.setCustomValidity('Enter an integer of at least 1.');omit.disabled=true;return;}h.setCustomValidity('');omit.disabled=false;omission=false;renderDiagnostic();});
    function renderGroups(){
      groups.replaceChildren();
      if(group.value===''){el('p','Select a categorical grouping to describe each feature separately on its observed finite values. Missing groups take precedence in disjoint exclusion counts.',groups);return;}
      const field=categorical[Number(group.value)];
      el('h4',`Marginal group summaries: ${field}`,groups);
      el('p','Separate marginal descriptions, not adjusted or causal effects. The group cohort can differ between features and from the joint covariance cohort.',groups);
      [[qns,state.query],[cns,c]].forEach(([ns,fid])=>{
        const r=window.valpasDiagnostics.groupSummary(layer,data.dataset,metadata,ns,fid,field,{include_fraction:fraction.checked});
        el('h4',`${fid} [${ns.modality}]`,groups);
        el('p',`Status: ${r.status}; reason: ${text(r.reason)}. Required: ${r.required_count}; known group: ${text(r.known_group_count)}; observed finite: ${text(r.observed_finite_count)}; included: ${text(r.included_count)}. Missing group excluded: ${text(r.exclusions.missing_group.count)}; not observed finite excluded: ${text(r.exclusions.not_observed_finite.count)}.`,groups);
        table(r.groups,groups,null,['group','count','mean']);
        el('p',`Between-group SS: ${text(r.between_group_ss)}; total SS: ${text(r.total_ss)}; fraction: ${text(r.between_group_fraction)}; ${r.fraction_status}; reason: ${text(r.fraction_reason)}.`,groups);
        detail('Exact marginal summary and exclusions',r,groups).className='group-exact';
      });
    }
    function renderPlots(){
      plots.replaceChildren();
      const field=color.value===''?null:fields[Number(color.value)], kind=field===null?null:metadata.fields[field];
      const required=data.dataset.observation_ids, displayOrder=[...required];
      if(order.value==='id')displayOrder.sort(codePointOrder);
      if(order.value==='metadata'){
        if(field===null)el('p','Select a color field to order by metadata; dataset order is retained.',plots,'notice');
        else displayOrder.sort((a,b)=>{const x=metadataValue(a,field),y=metadataValue(b,field);return x===y?codePointOrder(a,b):x===null?1:y===null?-1:kind==='continuous'?x-y:codePointOrder(x,y);});
      }
      const known=field===null?[]:required.map(s=>metadataValue(s,field)).filter(v=>v!==null);
      const categories=kind==='categorical'?[...new Set(known)].sort(codePointOrder):[];
      const categoryColors=new Map(categories.map((v,i)=>[v,`hsl(${i*137.508%360} 65% 38%)`]));
      const numericColor=scale(known,245,15);
      const pointColor=sid=>metadataValue(sid,field)===null?'#77818b':kind==='categorical'?categoryColors.get(metadataValue(sid,field)):`hsl(${numericColor(metadataValue(sid,field))} 70% 40%)`;
      const legend=el('div',null,plots,'metadata-legend');
      if(field===null)el('span','Feature role: blue query; purple candidate. ',legend);
      else {
        el('strong',`${field} (${kind}): `,legend);
        if(kind==='categorical')categories.forEach(v=>{const item=el('span',null,legend,'legend-item'),swatch=el('span',null,item,'legend-swatch');swatch.style.backgroundColor=categoryColors.get(v);el('span',v===''?'(empty string)':v,item);});
        else if(known.length){let min=Infinity,max=-Infinity;known.forEach(v=>{min=Math.min(min,v);max=Math.max(max,v);});el('span',`${min} (blue) → ${max} (red)${min===max?' — constant field':''}`,legend);}
        else el('span','No known values. ',legend);
        const missing=el('span',' Missing metadata: gray / dashed outline.',legend,'legend-missing');missing.title='Missing record, omitted field or explicit null';
      }
      el('p','Hollow orange: finite originally unobserved/imputed, excluded from all observed-only summaries. Hover shows exact observation ID, values and metadata/missing status. Display ordering does not change analysis cohorts.',plots);
      const p=d.profiles.find(r=>r.layer_id===layer.layer_id&&r.candidate_id===c);
      if(!p||p.reason&&p.reason!=='no_jointly_observed_finite_values'){el('p',`Plots unavailable: ${p?p.reason:'no profile metadata'}. No silent feature/cohort subsetting.`,plots,'notice');return;}
      const q=layer.features.find(f=>f.feature_id===state.query&&nsEqual(f.namespace,qns)), f=layer.features.find(f=>f.feature_id===c&&nsEqual(f.namespace,cns));
      el('p',`Jointly observed finite points: ${p.joint_observed_count}. Constant/near-empty flags appear above.`,plots);
      function decorate(n,i,imputed){const sid=layer.observation_ids[i];n.dataset.observationId=sid;if(field!==null){if(!imputed)n.style.fill=pointColor(sid);if(metadataValue(sid,field)===null)n.classList.add('metadata-missing');}}
      if(p.joint_indices.length){const s=makeSvg(720,240,plots,'Jointly observed scatter');axis(s,`${c} (${layer.units})`,`${state.query} (${layer.units})`);const xs=scale(p.joint_indices.map(i=>f.values[i]),60,670),ys=scale(p.joint_indices.map(i=>q.values[i]),195,40);p.joint_indices.forEach(i=>{const n=shape('circle',{cx:xs(f.values[i]),cy:ys(q.values[i]),r:4,class:'observed'},s);decorate(n,i,false);title(n,`${layer.observation_ids[i]}: query=${q.values[i]}, candidate=${f.values[i]}; ${hover(layer.observation_ids[i])}`);});}else el('p',p.reason,plots,'notice');
      const s=makeSvg(720,240,plots,'Sample-level observed and imputed profiles');axis(s,`${order.options[order.selectedIndex].textContent} →`,`Values (${layer.units}); shared scale`);
      const all=[...p.query_indices,...p.query_unobserved_indices].map(i=>q.values[i]).concat([...p.candidate_indices,...p.candidate_unobserved_indices].map(i=>f.values[i]));
      if(!all.length)return;
      const ys=scale(all,195,40), positions=new Map(displayOrder.map((sid,i)=>[sid,i]));
      [['query',q,'observed'],['candidate',f,'candidate']].forEach(([role,feature,cls])=>{[false,true].forEach(imputed=>{p[role+(imputed?'_unobserved_indices':'_indices')].forEach(i=>{const x=60+positions.get(layer.observation_ids[i])*610/Math.max(1,displayOrder.length-1);const n=shape('circle',{cx:x,cy:ys(feature.values[i]),r:imputed?5:3.5,class:imputed?'imputed':cls,'data-profile-role':role},s);decorate(n,i,imputed);title(n,`${layer.observation_ids[i]}: ${feature.feature_id}=${feature.values[i]}; ${imputed?'originally unobserved / imputed':'observed'}; ${hover(layer.observation_ids[i])}`);});});});
    }
    color.addEventListener('change',renderPlots);order.addEventListener('change',renderPlots);
    group.addEventListener('change',renderGroups);fraction.addEventListener('change',renderGroups);
    renderPlots();renderGroups();renderDiagnostic();
  }
  renderOverview();renderQueries();renderWorkspace();
  document.documentElement.dataset.reportReady='true';
})();
