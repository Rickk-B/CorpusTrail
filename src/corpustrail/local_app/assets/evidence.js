/* Operational evidence workflow, never a method-blind review client. */
(()=>{
  'use strict';
  const get=id=>document.getElementById(id), panel=get('evidence-acquisition');
  const match=location.pathname.match(/^\/papers\/([0-9a-f]{64})$/);
  if(!match||panel.hidden)return;
  const paper=match[1], session=document.querySelector('meta[name="corpustrail-session"]').content;
  const make=(tag,text='')=>{const node=document.createElement(tag);node.textContent=text;return node;};
  let availability,busy=false,command=null,timer=null,generation=0;
  const validity={verified:'Exact document identity verified',pending_identity:'Document identity unresolved — not trusted',mismatch:'Document identity mismatch — not trusted',invalid:'Invalid document — not trusted'};
  const outcomes={success:'Network request succeeded; verification is separate',not_found:'No eligible document returned by this resolver',retryable_error:'Resolver timed out, was unavailable or rate-limited',permanent_error:'Resolver could not complete the request',not_applicable:'Resolver is not applicable',parsing_failed:'Structured-text parsing failed'};
  const states={queued:'Retrieval queued',running:'Retrieval running',completed:'Retrieval operation completed — inspect document verification below',unsuccessful:'Retrieval unsuccessful — inspect resolver outcome below',interrupted:'Retrieval interrupted — inspect preserved work before an explicit new attempt',not_started:'Retrieval not started'};
  const say=text=>{get('evidence-result').textContent=text;};
  async function api(path,body){
    const options={headers:{'X-CorpusTrail-Session':session},cache:'no-store'};
    if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.headers['X-CorpusTrail-CSRF']=session;options.body=JSON.stringify({schema:'corpustrail-evidence-workflow/v1',...body});}
    const response=await fetch('/api/v1/evidence/'+path,options),data=await response.json();
    if(!response.ok){const error=Error(data.error.message);error.status=response.status;throw error;}return data;
  }
  function historyRows(items,replace=true){
    const list=get('evidence-history');if(replace)list.replaceChildren();
    for(const x of items){
      let description;
      if(x.kind==='representation')description=(x.representation==='structured_text'?'Structured text':x.representation==='abstract'?'Document abstract':'Retrieved document')+': '+(validity[x.artifact_validity]||'Inspect provenance')+(x.evidence_depth==='front_matter_only'?' · Front matter only, not document-body evidence':'');
      else if(x.kind==='acquisition_result')description=x.run_complete?'Resolver operation ended':outcomes[x.outcome]||'Inspect resolver outcome';
      else if(x.kind==='acquisition_started')description='Retrieval request started';
      else description='Evidence request recorded';
      list.append(make('li',description+' · '+(x.resolver||'Configured resolver')+' · '+(x.created_at||x.timestamp||'See provenance')+(x.attempt?' · Attempt '+x.attempt:'')));
    }
    if(!items.length&&replace)list.append(make('li','No evidence acquisition or document records are currently stored. This does not establish unavailability elsewhere.'));
  }
  async function load(offset=0,replace=true){
    const data=await api('papers/'+paper+'?offset='+offset);availability=data.availability;
    get('evidence-eligibility').textContent=availability.eligible?'Europe PMC can request structured text using '+availability.pmcid+'.':availability.reason;
    get('evidence-request').textContent=availability.notice+' Maximum '+availability.max_attempts+' attempts; retry wait bounded to '+availability.max_retry_wait_seconds+' seconds. '+availability.enrichment;
    get('retrieve-evidence').hidden=!availability.eligible;get('retrieve-evidence').disabled=busy;
    if(data.abstract_source)get('abstract-source').textContent=data.abstract_source.origin+' · '+data.abstract_source.provider+' · '+data.abstract_source.verification;
    historyRows(data.activity.items,replace);
    get('more-evidence').hidden=data.activity.next_offset===null;
    get('more-evidence').onclick=()=>load(data.activity.next_offset,false).catch(e=>say(e.message));
  }
  async function operations(offset=0,replace=true){
    const data=await api('papers/'+paper+'/history?offset='+offset),list=get('evidence-operations');
    if(replace)list.replaceChildren();
    for(const item of data.items){const li=make('li'),button=make('button',(states[item.status]||item.status)+' · '+item.created_at);button.type='button';button.onclick=()=>inspect(item.handle).catch(e=>say(e.message));li.append(button);list.append(li);}
    get('more-operations').hidden=data.next_offset===null;
    get('more-operations').onclick=()=>operations(data.next_offset,false).catch(e=>say(e.message));
  }
  async function inspect(handle){
    generation++;if(timer)clearTimeout(timer);
    const current=generation,data=await api('operations/'+handle);
    say(states[data.status]||data.status);historyRows(data.activity.items);
    busy=['queued','running'].includes(data.status);get('retrieve-evidence').disabled=busy;
    if(busy){timer=setTimeout(()=>{if(current===generation)inspect(handle).catch(e=>say(e.message+' No automatic retry occurs.'));},1200);}
    else{command=null;await load();await operations();if(globalThis.corpustrailRefreshEvidence)await globalThis.corpustrailRefreshEvidence();}
  }
  get('retrieve-evidence').onclick=async()=>{
    if(busy)return;busy=true;get('retrieve-evidence').disabled=true;
    // Retain the same command on an uncertain HTTP response. Backend replay
    // returns its original operation; it never issues another network request.
    if(!command)command={paper,request_id:crypto.randomUUID(),eligibility_hash:availability.eligibility_hash,confirm_external:true};
    try{const result=await api('start',command);await inspect(result.handle);}
    catch(error){busy=false;get('retrieve-evidence').disabled=false;
      say(error.message+' Inspect operation history before retrying; refresh if settings changed.');
      if(error.status===400||error.status===403){command=null;}
      await operations().catch(()=>{});
    }
  };
  async function provenance(offset=0,replace=true){
    const data=await api('papers/'+paper+'/provenance?offset='+offset);
    if(replace)get('evidence-raw').textContent='';get('evidence-raw').textContent+=JSON.stringify(data.activity.items,null,2)+'\n';
    get('more-evidence-provenance').hidden=data.activity.next_offset===null;
    get('more-evidence-provenance').onclick=()=>provenance(data.activity.next_offset,false).catch(e=>say(e.message));
  }
  get('evidence-provenance').onclick=()=>provenance().catch(e=>say(e.message));
  Promise.all([load(),operations()]).catch(error=>say(error.message));
})();
