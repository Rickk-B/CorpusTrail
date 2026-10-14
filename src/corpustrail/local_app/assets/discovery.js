'use strict';
const get = id => document.getElementById(id);
const make = (tag, text='') => { const element=document.createElement(tag); element.textContent=text; return element; };
const session = document.querySelector('meta[name="corpustrail-session"]').content;
const schema = 'corpustrail-discovery-workflow/v1';
let configuration, view=null, previewNonce=null, busy=false, timer=null, generation=0;
const messages = {prepared:'Awaiting approval', approved:'Approved — not yet run', queued:'Queued', running:'Running', completed:'Completed bounded search', partial:'Completed with errors / partial', failed:'Failed — inspect preserved work', interrupted:'Interrupted — no automatic replay', cancelled:'Stopped between providers', invalidated:'Edited — a new preview is required'};
const outcomes = {exhausted:'No further results reported',truncated_page_limit:'Approved page limit reached; more results may exist',truncated_provider_limit:'Provider result limit reached',retryable_error:'Temporary failure or rate limit; retries exhausted or blocked',permanent_error:'Request rejected — inspect provenance',not_found:'Database returned not found',malformed_response:'Response could not be normalized',requires_configuration:'Credential configuration needed'};
function message(value) { get('message').textContent=value; }
async function api(path, body) {
  const options={headers:{'X-CorpusTrail-Session':session},cache:'no-store'};
  if (body!==undefined) { options.method='POST'; options.headers['Content-Type']='application/json'; options.headers['X-CorpusTrail-CSRF']=session; options.body=JSON.stringify({schema,...body}); }
  const response=await fetch('/api/v1/discovery/'+path,options), value=await response.json();
  if (!response.ok) throw Error(value.error.message);
  return value;
}
function stopPolling() { generation++; if(timer)clearTimeout(timer); timer=null; }
function searchFields() {
  return {config_event_id:configuration.config_event_id, query:get('query').value,
    providers:[...document.querySelectorAll('[data-provider]')].filter(e=>e.checked).map(e=>e.value),
    bounds:Object.fromEntries(Object.keys(configuration.bounds).map(k=>[k,Number(get('bound-'+k).value)]))};
}
function setFields(plan) {
  get('query').value=plan.query;
  for(const e of document.querySelectorAll('[data-provider]')) e.checked=plan.providers.some(p=>p.provider===e.value)&&!e.disabled;
  for(const [key,value] of Object.entries(plan.bounds))get('bound-'+key).value=value;
}
async function action(work) {
  if(busy)return; busy=true;
  for(const id of ['preview','approve','run','edit','repeat','cancel'])get(id).disabled=true;
  try {await work();} catch(error){message(error.message);} finally {
    busy=false; for(const id of ['preview','approve','run','edit','repeat','cancel'])get(id).disabled=false;
  }
}
function renderPlan(value) {
  if(!view||view.handle!==value.handle)get('plan-advanced').open=false;
  view=value;get('plan-section').hidden=false;get('plan-query').textContent=value.plan.query;
  get('plan-providers').replaceChildren();get('provenance-provider').replaceChildren();
  for(const provider of value.plan.providers) {
    const card=make('article'), heading=make('h3',provider.label);card.className='discovery-provider';card.append(heading);
    const dl=make('dl');dl.className='plan-summary';
    const names={search:'Search query','query.bibliographic':'Bibliographic search query',query:'Search query',per_page:'Records per page',rows:'Records per page',pageSize:'Records per page',limit:'Records per page',cursor:'Initial page cursor',cursorMark:'Initial page cursor',offset:'Initial result offset',format:'Response format',resultType:'Response detail',fields:'Requested metadata fields'};
    for(const parameter of provider.request_preview.parameters)dl.append(make('dt',names[parameter.name]||parameter.name),make('dd',parameter.value));
    for(const [label,key] of [['Maximum pages','max_pages'],['Maximum attempts per request','max_attempts'],['Retry delay (seconds)','retry_delay_seconds'],['Maximum allowed retry wait (seconds)','max_retry_wait_seconds']])dl.append(make('dt',label),make('dd',String(provider.plan[key])));
    const runtime=make('p',provider.request_preview.runtime_components);runtime.className='muted';card.append(dl,runtime);
    get('plan-providers').append(card);
    const option=make('option',provider.label);option.value=provider.provider;get('provenance-provider').append(option);
  }
  get('plan-details').textContent=JSON.stringify(value.plan,null,2);
  get('approval-providers').textContent=value.plan.providers.map(provider=>provider.label).join(', ');
  get('plan-notice').textContent=messages[value.status]+'. '+(value.execution_available?'':'This plan cannot start; prepare a new preview if settings changed. ')+value.notice;
  get('approval-area').hidden=!(value.status==='prepared'&&previewNonce&&value.execution_available);
  get('run').hidden=!(value.status==='approved'&&value.execution_available);
  get('edit').hidden=!['prepared','approved'].includes(value.status);
  get('search-setup').hidden=true;
  get('job-section').hidden=!['queued','running','completed','partial','failed','interrupted','cancelled'].includes(value.status);
  if(!get('job-section').hidden)renderJob(value);
}
function renderJob(value) {
  get('job-status').textContent=messages[value.status]+' · '+value.providers_finished+'/'+value.providers_total+' providers finished'+(value.elapsed_seconds===null?'':' · '+value.elapsed_seconds+' seconds elapsed');
  get('provider-progress').replaceChildren();
  for(const p of value.providers)get('provider-progress').append(make('li',p.label+': '+p.status+' · '+p.observations_preserved+' observations preserved · '+p.physical_requests_started+' request attempts started'+(p.completion?' · '+(outcomes[p.completion.outcome]||p.completion.outcome):'')+(p.outcome?.diagnostic?' · '+p.outcome.message:'')));
  get('results').replaceChildren();
  const labels={observations_preserved:'Provider observations preserved',linked_observations:'Observations linked to publications',unique_publications:'Unique publications linked',publications_created_by_run:'Publications created by this search',previously_known_publications:'Previously known publications',observations_not_linked:'Observations not linked (pending/identity issues)',provider_errors:'Provider errors / interrupted requests'};
  for(const [key,label] of Object.entries(labels))get('results').append(make('dt',label),make('dd',String(value.summary[key])));
  get('cancel').hidden=!value.cancellation_available||value.cancel_requested;
  get('cancel-notice').textContent=value.cancel_requested?'Stop requested. The current bounded provider operation may finish before stopping.':'';
}
async function paperPage(offset=0, replace=true) {
  const result=await api('plans/'+view.handle+'/papers?offset='+offset);
  if(replace)get('result-papers').replaceChildren();
  for(const item of result.items){const li=make('li'),link=make('a',item.title);link.href=item.url;li.append(link);get('result-papers').append(li);}
  get('more-papers').hidden=result.next_offset===null;get('more-papers').onclick=()=>paperPage(result.next_offset,false).catch(e=>message(e.message));
}
async function historyPage(offset=0, replace=true) {
  const result=await api('history?offset='+offset);if(replace)get('history').replaceChildren();
  for(const item of result.items){const li=make('li'),button=make('button',item.query+' · '+messages[item.status]+' · '+item.created_at);button.type='button';
    button.onclick=()=>action(async()=>{stopPolling();previewNonce=null;renderPlan(await api('plans/'+item.handle));await paperPage();poll();});li.append(button);get('history').append(li);}
  get('more-history').hidden=result.next_offset===null;get('more-history').onclick=()=>historyPage(result.next_offset,false).catch(e=>message(e.message));
}
function poll() {
  if(!view||!['queued','running'].includes(view.status))return;
  const current=generation, handle=view.handle;
  timer=setTimeout(async()=>{
    try {const next=await api('plans/'+handle);if(current!==generation)return;renderPlan(next);
      if(!['queued','running'].includes(next.status)){await paperPage();await historyPage();}else poll();}
    catch(error){message(error.message+' Reopen this search from history; no automatic execution retry occurs.');}
  },1500);
}
get('search-form').onsubmit=event=>{event.preventDefault();action(async()=>{
  stopPolling();const result=await api('prepare',{request_id:crypto.randomUUID(),...searchFields()});previewNonce=result.preview_nonce;
  renderPlan(result);await historyPage();message('Exact plan saved locally. No database has been contacted.');
});};
get('approve').onclick=()=>action(async()=>{
  // This deliberate action authorizes BOTH disclosed operations for this preview.
  // The backend still requires both flags, the one-time nonce and exact plan hash.
  if(!view||view.status!=='prepared'||!previewNonce||get('approval-area').hidden)throw Error('Review a current exact plan before explicitly approving both operations.');
  renderPlan(await api('approve',{handle:view.handle,request_id:crypto.randomUUID(),preview_nonce:previewNonce,confirm_external:true,approve_identities:true}));
  previewNonce=null;message('Plan approved. Run Discovery is a separate explicit action.');await historyPage();
});
get('run').onclick=()=>action(async()=>{renderPlan(await api('start',{handle:view.handle,request_id:crypto.randomUUID()}));message('The approved exact search has started.');poll();if(!['queued','running'].includes(view.status))await paperPage();await historyPage();});
get('edit').onclick=()=>action(async()=>{await api('invalidate',{handle:view.handle});setFields(view.plan);stopPolling();view=null;previewNonce=null;get('plan-section').hidden=true;get('job-section').hidden=true;get('search-setup').hidden=false;message('Previous preview/approval invalidated. Preview edited settings before approval.');get('query').focus();await historyPage();});
get('repeat').onclick=()=>action(async()=>{setFields(view.plan);stopPolling();view=null;previewNonce=null;get('plan-section').hidden=true;get('job-section').hidden=true;get('search-setup').hidden=false;message('These settings are a new search draft. Preview and approve it; nothing has been rerun.');get('query').focus();});
get('cancel').onclick=()=>action(async()=>{renderPlan(await api('cancel',{handle:view.handle}));poll();});
async function provenancePage(offset=0, replace=true) {
  const result=await api('plans/'+view.handle+'/provenance?provider='+encodeURIComponent(get('provenance-provider').value)+'&offset='+offset);
  if(replace)get('provenance').textContent='';get('provenance').textContent+=JSON.stringify(result.items,null,2)+'\n';
  get('more-provenance').hidden=result.next_offset===null;get('more-provenance').onclick=()=>provenancePage(result.next_offset,false).catch(e=>message(e.message));
}
get('show-provenance').onclick=()=>provenancePage().catch(e=>message(e.message));
async function initialize() {
  configuration=await api('configuration');
  for(const c of configuration.concepts){const option=make('option',c.label);option.value=c.label;get('concept').append(option);}
  get('concept').onchange=()=>{get('query').value=get('concept').value;};
  for(const p of configuration.providers){const div=make('div');div.className='service-option';const label=make('label',p.label);label.className='choice';
    const input=make('input');input.type='checkbox';input.value=p.id;input.dataset.provider=p.id;input.disabled=!p.ready;label.prepend(input);div.append(label,make('p',p.reason+(p.credential_env?' Environment variable: '+p.credential_env:'')));get('providers').append(div);}
  const labels={page_size:'Requested records per page',max_pages:'Maximum pages per database',max_attempts:'Maximum attempts per request',retry_delay_seconds:'Retry delay (seconds)',max_retry_wait_seconds:'Maximum allowed retry wait (seconds)'};
  for(const [key,value] of Object.entries(configuration.bounds)){const label=make('label',labels[key]),input=make('input');input.id='bound-'+key;input.type='number';input.value=value;input.required=true;input.min=['retry_delay_seconds','max_retry_wait_seconds'].includes(key)?0:1;input.max=key==='max_attempts'?3:key==='retry_delay_seconds'?30:key==='max_retry_wait_seconds'?60:100;label.append(input);get('bounds').append(label);}
  await historyPage();
}
initialize().catch(error=>message(error.message));
