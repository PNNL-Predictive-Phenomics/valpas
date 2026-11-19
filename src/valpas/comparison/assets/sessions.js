/* Portable user-authored state. No storage, network or filesystem writes. */
(() => {
  'use strict';
  window.valpasSessions = function(data) {
    const scope=data.session_contract.scope;
    const clone=v=>JSON.parse(JSON.stringify(v));
    const assert=(ok,message)=>{if(!ok)throw Error(message);};
    const order=(a,b)=>{const x=Array.from(a,c=>c.codePointAt(0)),y=Array.from(b,c=>c.codePointAt(0));for(let i=0;i<Math.min(x.length,y.length);i++)if(x[i]!==y[i])return x[i]-y[i];return x.length-y.length;};
    const canonical=v=>v===null||typeof v!=='object'?JSON.stringify(v):Array.isArray(v)?'['+v.map(canonical).join(',')+']':'{'+Object.keys(v).sort(order).map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';
    const safe=v=>canonical(v).replace(/&/g,'\\u0026').replace(/</g,'\\u003c').replace(/>/g,'\\u003e').replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
    const hash=async v=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(v)))),b=>b.toString(16).padStart(2,'0')).join('');
    const keys=(v,names)=>assert(v!==null&&typeof v==='object'&&!Array.isArray(v)&&canonical(Object.keys(v).sort())===canonical(names.split(' ').sort()),'Missing or unknown nested fields');
    const member=(v,choices,nullable=false)=>assert(nullable&&v===null||typeof v==='string'&&choices.includes(v),'Unknown ID/setting or outside embedded scope');
    const list=(v,choices,empty=true)=>{assert(Array.isArray(v)&&(empty||v.length>0)&&new Set(v).size===v.length,'Expected distinct ID list');v.forEach(x=>member(x,choices));};
    const integer=v=>assert(Number.isSafeInteger(v)&&v>=1,'Expected positive safe integer');
    const bool=v=>assert(typeof v==='boolean','Expected boolean');
    const string=v=>assert(typeof v==='string','Expected text');
    function view(v) {
      keys(v,'depth query candidate pair search candidateSearch hidden pins referenceEndpoint evidenceFilter selectedLayer layers queryOrder candidateOrder');
      integer(v.depth);assert(v.depth<=scope.max_depth,'Depth outside embedded scope');
      member(v.query,scope.query_ids,true);
      member(v.candidate,(scope.candidates.find(r=>r.query_id===v.query)||{candidate_ids:[]}).candidate_ids,true);
      if(v.pair!==null){list(v.pair,scope.output_ids);assert(v.pair.length===2,'Expected output pair');}
      string(v.search);string(v.candidateSearch);list(v.hidden,scope.output_ids);
      list(v.pins,[...new Set(scope.candidates.flatMap(r=>r.candidate_ids))]);
      member(v.referenceEndpoint,scope.reference_endpoint_ids,!scope.reference_endpoint_ids.length);
      member(v.evidenceFilter,scope.reference_endpoint_ids.length?['all','supported','unsupported']:['all']);
      member(v.selectedLayer,scope.layer_ids,true);
      member(v.queryOrder,['id_asc','id_desc']);member(v.candidateOrder,['id_asc','id_desc']);
      assert(Array.isArray(v.layers)&&canonical(v.layers.map(l=>l.layer_id))===canonical(scope.layer_ids),'Layer settings must match embedded scope');
      v.layers.forEach(l=>{keys(l,'layer_id color group order include_fraction h omission');member(l.color,Object.keys(scope.metadata_fields),true);member(l.group,Object.keys(scope.metadata_fields).filter(f=>scope.metadata_fields[f]==='categorical'),true);member(l.order,['dataset','id','metadata']);bool(l.include_fraction);integer(l.h);bool(l.omission);});
    }
    // Parse JSON grammar first to reject duplicate object keys at every depth.
    function parse(raw) {
      let i=0;
      const ws=()=>{while(/[\x20\t\r\n]/.test(raw[i]||'!'))i++;};
      const token=()=>{const start=i;assert(raw[i++]==='"','Expected JSON string');while(i<raw.length){const c=raw[i++];if(c==='"')return JSON.parse(raw.slice(start,i));if(c==='\\')i++;}throw Error('Unterminated string');};
      function value(){ws();if(raw[i]==='{'){i++;ws();const seen=new Set();if(raw[i]==='}'){i++;return;}while(true){ws();const key=token();assert(!seen.has(key),'Duplicate JSON key');seen.add(key);ws();assert(raw[i++]===':','Expected colon');value();ws();if(raw[i]==='}'){i++;return;}assert(raw[i++]===',','Expected comma');}}else if(raw[i]==='['){i++;ws();if(raw[i]===']'){i++;return;}while(true){value();ws();if(raw[i]===']'){i++;return;}assert(raw[i++]===',','Expected comma');}}else if(raw[i]==='"')token();else{const m=raw.slice(i).match(/^(?:null|true|false|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/);assert(m,'Invalid JSON value');i+=m[0].length;}}
      value();ws();assert(i===raw.length,'Trailing JSON data');return JSON.parse(raw);
    }
    async function validate(doc,kind) {
      keys(doc,'schema_version kind comparison_id content_id pool_policy scope view notes decisions integrity_sha256');
      assert(doc.schema_version===1&&doc.kind===kind,'Unsupported schema/kind; no migration');
      assert(doc.comparison_id===data.comparison_id,'Comparison ID mismatch');
      assert(doc.content_id===data.session_content_id&&doc.pool_policy===data.analysis_settings.pool_policy,'Content binding mismatch (profiles/metadata/references)');
      assert(canonical(doc.scope)===canonical(scope),'Report scope changed or unknown fields: re-export or explicitly rebind scope in Python');
      view(doc.view);string(doc.notes);assert(Array.isArray(doc.decisions),'Expected decision list');
      const seen=new Set();
      doc.decisions.forEach(d=>{
        keys(d,'decision_id comparison_id query_id candidate_id pool_policy depth inspected_output_ids decision rationale timestamp view');
        string(d.decision_id);assert(d.decision_id.length>0&&!seen.has(d.decision_id),'Duplicate/empty decision ID');seen.add(d.decision_id);
        view(d.view);member(d.query_id,scope.query_ids);integer(d.depth);
        assert(d.comparison_id===doc.comparison_id&&d.pool_policy===doc.pool_policy&&d.query_id===d.view.query&&d.depth===d.view.depth,'Decision context mismatch');
        member(d.decision,['investigate','retain_alternative','abstain']);
        assert(d.decision==='abstain'?d.candidate_id===null&&d.view.candidate===null:d.candidate_id!==null&&d.candidate_id===d.view.candidate,'Decision candidate mismatch');
        list(d.inspected_output_ids,scope.output_ids,false);
        assert(canonical(d.inspected_output_ids)===canonical(scope.output_ids.filter(o=>!d.view.hidden.includes(o))),'Inspected outputs differ from snapshot');
        string(d.rationale);assert(d.rationale.trim().length>0,'A meaningful rationale is required');
        assert(typeof d.timestamp==='string'&&/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(d.timestamp),'Expected UTC timestamp with seconds and Z');
        const date=new Date(d.timestamp);assert(Number.isFinite(date.getTime())&&date.getUTCFullYear()>=1970&&date.toISOString().slice(0,19)===d.timestamp.slice(0,19),'Invalid calendar timestamp');
      });
      const body={...doc};delete body.integrity_sha256;
      assert(await hash(body)===doc.integrity_sha256,'Content checksum mismatch');
      return clone(doc);
    }
    async function makeDocument(kind,v,notes,decisions) {
      const doc={schema_version:1,kind,comparison_id:data.comparison_id,content_id:data.session_content_id,pool_policy:data.analysis_settings.pool_policy,scope:clone(scope),view:clone(v),notes,decisions:clone(decisions)};
      doc.integrity_sha256=await hash(doc);return validate(doc,kind);
    }
    function download(name,content,type) {
      const url=URL.createObjectURL(new Blob([content],{type})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
    }
    function csv(doc) {
      const columns=['decision_id','comparison_id','query_id','candidate_id','pool_policy','depth','inspected_output_ids','decision','rationale','timestamp','view'];
      const quote=s=>'"'+s.replace(/"/g,'""')+'"';
      return columns.join(',')+'\r\n'+doc.decisions.map(d=>columns.map(k=>quote("'"+(typeof d[k]==='string'?d[k]:canonical(d[k])))).join(',')).join('\r\n')+'\r\n';
    }
    return {parse,validate,document:makeDocument,download,safe,csv,clone,view};
  };
})();
