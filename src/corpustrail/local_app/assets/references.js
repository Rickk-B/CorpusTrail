'use strict';
// Presentation only: the scientific reference service owns all saved state.
const el=id=>document.getElementById(id),node=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
const token=document.querySelector('meta[name="corpustrail-session"]').content,schema='corpustrail-local-references/v1';
let config,selected,parent=null,staged=[],busy=false,request=null,preview=null,contextRequest=null,contextPreview=null,target=null,currentContext=null;
let versionPage,memberPage,changePage,contextPage,decisionPage,populationPage,populationCutoff,paperCursor,targetCursor;
let memberStart=0,changeStart=0,decisionStart=0;
const handle=id=>id.split(':')[1],say=text=>{el('reference-message').textContent=text;};
async function api(path,body=null){
  const headers={'X-CorpusTrail-Session':token};if(body)Object.assign(headers,{'Content-Type':'application/json','X-CorpusTrail-CSRF':token});
  const response=await fetch('/api/v1/'+path,{method:body?'POST':'GET',headers,cache:'no-store',body:body?JSON.stringify({schema,...body}):undefined});
  const value=await response.json();if(!response.ok)throw Error(value.error.message);return value;
}
const fail=error=>say('Not completed: '+error.message+' A lost response can leave the outcome uncertain. Inspect saved history before explicitly retrying; no automatic retry occurs. Unsaved input is retained in this page.');
async function guarded(action){if(busy)return;busy=true;document.querySelectorAll('button').forEach(b=>{b.disabled=true;});try{await action();}catch(error){fail(error);}finally{busy=false;document.querySelectorAll('button').forEach(b=>{b.disabled=false;});}}
function invalidate(){request=null;preview=null;el('reference-preview').hidden=true;}
function invalidateContext(){contextRequest=null;contextPreview=null;el('context-preview').hidden=true;}
function button(text,action){const b=node('button',text);b.type='button';b.onclick=()=>guarded(action);return b;}
function previous(nextId,label,action){const b=button(label,action);b.id=nextId+'-previous';b.hidden=true;el(nextId).before(b);}
function describeCounts(id,counts){el(id).replaceChildren();for(const [key,label] of [['paper_count','Canonical publications'],['assignment_count','Active assignments'],['in_scope','Known in-scope'],['out_of_scope','Known out-of-scope'],['conflicts','Conflicting publications'],['unattested','Unattested proposals']])el(id).append(node('dt',label),node('dd',String(counts[key]??0)));}
function renderStaged(){
  el('reference-staged').replaceChildren();if(!staged.length)el('reference-staged').append(node('p','No changes staged.'));
  staged.forEach((item,index)=>{const p=node('p',item.title+' · '+(item.change.action==='remove'?'Remove assignment':item.change.label==='in_scope'?'Known in-scope':'Known out-of-scope')+(item.change.action==='assign'?' · Evidence used: '+(item.change.evidence_used.join(', ')||'none')+(item.change.source_event_id?' · Explicit corpus-event lineage':''):'')+' ');p.append(button('Unstage',async()=>{staged.splice(index,1);el('reference-attest').checked=false;invalidate();renderStaged();}));el('reference-staged').append(p);});
}
function stage(change,title){if(staged.length>=20)throw Error('Commit or clear this 20-change batch before staging more.');staged.push({change,title});el('reference-attest').checked=false;invalidate();renderStaged();say('Change staged only; no reference version or corpus decision saved.');}
function basisOptions(select,item){
  select.replaceChildren();const empty=node('option','Choose evidence actually used');empty.value='';empty.disabled=true;empty.selected=true;select.append(empty);
  for(const [value,text,available] of [['metadata','Bibliographic metadata',true],['abstract','Available abstract',item.evidence.abstract_available],['structured_text','Verified structured text',item.evidence.verified_structured_text]])if(available){const o=node('option',text);o.value=value;select.append(o);}
}
async function findPapers(forTarget=false,more=false){
  const data=await api('papers?'+new URLSearchParams({q:el(forTarget?'context-target-search':'reference-search').value.trim(),limit:10,...(more?{cursor:forTarget?targetCursor:paperCursor}:{})}));
  const box=el(forTarget?'context-choices':'reference-choices');box.replaceChildren();
  for(const item of data.items){
    const row=node('article','');row.className='card';row.append(node('h3',item.bibliography.title||'Untitled publication'));const publication=node('a','Inspect Publication and Evidence');publication.href='/papers/'+item.handle;row.append(publication);
    if(forTarget)row.append(button('Select Target',async()=>{target='ct-paper:'+item.handle;basisOptions(el('context-basis'),item);el('context-selected').textContent='Target: '+(item.bibliography.title||'Untitled publication');invalidateContext();}));
    else{
      const label=node('label','Evidence actually used'),select=document.createElement('select');select.setAttribute('aria-label','Evidence actually used for '+(item.bibliography.title||'publication'));basisOptions(select,item);label.append(select);row.append(label);
      const add=(value,source=null)=>{if(!select.value)throw Error('Choose the evidence actually used before staging a label.');stage({action:'assign',paper_id:'ct-paper:'+item.handle,label:value,evidence_used:[select.value],supersedes:[],source_assignment_ids:[],source_event_id:source,source_artifact_sha256:null,source_record:null},item.bibliography.title||'Untitled publication');};
      const actions=node('div','');actions.className='pager';actions.append(button('Stage Known In-scope',async()=>add('in_scope')),button('Stage Known Out-of-scope',async()=>add('out_of_scope')));
      if(['included','excluded'].includes(item.membership.state))actions.append(button('Stage Current Corpus Decision as Reference',async()=>{const source=await api('references/papers/'+item.handle);if(!['included','excluded'].includes(source.state))throw Error('The corpus decision changed; inspect it before staging.');add(source.state==='included'?'in_scope':'out_of_scope',source.source_event_id);}));
      row.append(actions);
    }box.append(row);
  }
  if(!data.items.length)box.append(node('p','No collected publications match. No provider search was performed.'));
  if(forTarget)targetCursor=data.next_cursor;else paperCursor=data.next_cursor;el(forTarget?'context-more-papers':'reference-more-papers').hidden=data.next_cursor===null;
}
async function configuration(){config=await api('references/configuration');el('reference-upgrade').hidden=config.available;el('reference-editor').hidden=!config.available;}
async function versions(more=false,back=false){
  const offset=back?Math.max(0,versionPage.current-20):more?versionPage.offset:0;
  const data=await api('references/versions'+(more||back?'?offset='+offset+'&cutoff='+versionPage.cutoff:''));
  el('reference-empty').textContent=data.total?data.total+' saved immutable versions.':'No saved reference versions. Opening this workspace creates no labels.';
  const box=el('reference-versions');box.replaceChildren();for(const item of data.items){const row=node('article','');row.append(node('h3',item.name+' · Version '+item.version),node('p',item.counts.paper_count+' canonical publications · '+item.counts.assignment_count+' assignments · '+item.actor+' · '+item.created_at),button('Inspect Reference Version',()=>inspectVersion(item.version_id)));box.append(row);}
  versionPage={current:offset,offset:data.next_offset,cutoff:data.cutoff};el('reference-more-versions').hidden=data.next_offset===null;el('reference-more-versions-previous').hidden=!offset;
}
async function members(offset=0){
  const data=await api('references/versions/'+handle(selected.version_id)+'/members?'+new URLSearchParams({offset,limit:20,...(el('reference-label').value?{label:el('reference-label').value}:{})}));
  const box=el('reference-members');box.replaceChildren();for(const item of data.items){
    const row=node('article','');row.className='card';const title=item.bibliography.title||'Untitled publication';row.append(node('h3',title),node('p',(item.label==='in_scope'?'In-scope':'Out-of-scope')+' · '+(item.conflicting?'Conflicting labels — ineligible':item.eligible?'Human-attested — eligible':'Unattested proposal — ineligible')),node('p','By '+item.actor+' · '+item.created_at),node('p',item.rationale||'No rationale recorded.'),node('p','Evidence used: '+(item.evidence_used.join(', ')||'none')));
    const extent=document.createElement('select');extent.setAttribute('aria-label','Evidence actually used for correction of '+title);for(const [value,text] of [['','Choose correction evidence actually used'],['metadata','Current bibliographic metadata'],['none','No evidence claim — label correction only']]){const o=node('option',text);o.value=value;if(!value){o.disabled=true;o.selected=true;}extent.append(o);}row.append(extent);
    row.append(button('Inspect Assignment Provenance',async()=>{const value=await api('references/versions/'+handle(selected.version_id)+'/assignments/'+handle(item.assignment_id));const details=node('details','');details.open=true;const pre=node('pre',JSON.stringify(value,null,2));pre.className='reference-raw';details.append(node('summary','Frozen assignment evidence and lineage'),pre);row.append(details);}),button('Stage Removal in Successor',async()=>{chooseSuccessor();const reason=el('reference-rationale').value.trim();if(!reason)throw Error('Enter an explicit removal rationale in the batch editor.');stage({action:'remove',assignment_id:item.assignment_id,reason},title);}),button('Stage Corrected Label in Successor',async()=>{
      chooseSuccessor();const reason=el('reference-rationale').value.trim();if(!reason)throw Error('Enter a correction rationale in the batch editor.');
      if(!extent.value)throw Error('Explicitly choose the evidence actually used for this correction; old evidence use is not re-attested automatically.');
      stage({action:'assign',paper_id:item.paper_id,label:item.label==='in_scope'?'out_of_scope':'in_scope',evidence_used:extent.value==='none'?[]:[extent.value],supersedes:[item.assignment_id],source_assignment_ids:[item.assignment_id],source_event_id:null,source_artifact_sha256:null,source_record:null},title);
    }));box.append(row);
  }
  if(!data.total)box.append(node('p','No assignments under this filter.'));memberStart=offset;memberPage=data.next_offset;el('reference-more-members').hidden=memberPage===null;el('reference-more-members-previous').hidden=!offset;
}
async function changes(offset=0){const data=await api('references/versions/'+handle(selected.version_id)+'/provenance?offset='+offset);el('reference-changes').replaceChildren(...data.items.map(v=>node('pre',JSON.stringify(v,null,2))));changeStart=offset;changePage=data.next_offset;el('reference-more-changes').hidden=changePage===null;el('reference-more-changes-previous').hidden=!offset;}
async function inspectVersion(vid){
  selected=await api('references/versions/'+handle(vid));el('reference-detail').hidden=false;el('reference-detail-heading').textContent=selected.name+' · Version '+selected.version;
  el('reference-detail-status').textContent='Immutable · '+selected.actor+' · '+selected.created_at;describeCounts('reference-detail-counts',selected.counts);el('reference-header').textContent=JSON.stringify(selected,null,2);el('reference-provenance').open=false;el('context-builder').open=false;invalidateContext();await members();history.replaceState(null,'','/references#'+handle(vid));el('reference-detail-heading').focus();
}
function chooseSuccessor(){if(parent!==selected.version_id&&staged.length)throw Error('Clear or commit the other staged batch before choosing a successor.');parent=selected.version_id;el('reference-name').value=selected.name;el('reference-parent').textContent='Successor of '+selected.name+' · Version '+selected.version+'. Existing versions remain unchanged.';el('reference-new').hidden=false;invalidate();}
el('reference-form').addEventListener('input',event=>{invalidate();if(event.target.id!=='reference-attest')el('reference-attest').checked=false;});
el('reference-form').onsubmit=event=>{event.preventDefault();guarded(async()=>{
  if(!staged.length)throw Error('Stage at least one explicit change.');await configuration();const actor=el('reference-actor').value;
  request={request_id:crypto.randomUUID().replaceAll('-',''),name:el('reference-name').value,actor,parent,config_event_id:config.config_event_id,created_at:config.suggested_time,
    changes:staged.map(({change})=>change.action==='remove'?change:{...change,rationale:el('reference-rationale').value,producer:{type:'human',id:actor,version:'manual/v1'},human_attested:el('reference-attest').checked})};
  const candidate=request,data=await api('references/preview',request);if(request!==candidate)return;preview=data.reference;describeCounts('reference-preview-counts',preview.counts);el('reference-preview-scope').textContent='Scope: '+preview.definition.scope+' · Policy: '+preview.definition.policy_id;el('reference-preview').hidden=false;el('reference-preview-heading').focus();say('Preview only. No reference version, human observation or corpus-membership decision created.');
});};
el('reference-commit').onclick=()=>guarded(async()=>{if(!request||!preview)return;const data=await api('references/commit',{...request,expected_preview_sha256:preview.preview_sha256});staged=[];parent=null;el('reference-attest').checked=false;invalidate();renderStaged();await versions();await inspectVersion(data.reference.version_id);say('Reference version committed. Corpus membership and review observations were not changed.');});
el('reference-edit').onclick=()=>{invalidate();el('reference-name').focus();};
el('reference-new').onclick=()=>guarded(async()=>{if(staged.length)throw Error('Clear or commit staged changes first.');parent=null;el('reference-parent').textContent='New independent collection.';el('reference-new').hidden=true;invalidate();});
el('reference-successor').onclick=()=>guarded(async()=>{chooseSuccessor();el('reference-rationale').focus();});
el('reference-label').onchange=()=>guarded(()=>members());el('reference-more-members').onclick=()=>guarded(()=>members(memberPage));
el('reference-provenance').addEventListener('toggle',()=>{if(el('reference-provenance').open)guarded(()=>changes());});el('reference-more-changes').onclick=()=>guarded(()=>changes(changePage));
el('reference-verify').onclick=()=>guarded(async()=>{await api('references/verify',{version_id:selected.version_id});say('Stored reference integrity verified. This is not evidence verification or membership publication.');});
el('reference-find').onclick=()=>guarded(()=>findPapers());el('reference-more-papers').onclick=()=>guarded(()=>findPapers(false,true));el('reference-more-versions').onclick=()=>guarded(()=>versions(true));
el('reference-enable').onclick=()=>guarded(async()=>{await api('references/upgrade',{request_id:crypto.randomUUID().replaceAll('-',''),confirm_backup:true,project_id:config.project_id,config_event_id:config.config_event_id});await configuration();say('Reference storage enabled after a project-local database backup.');});
async function populations(more=false){const data=await api('populations/versions'+(more?'?offset='+populationPage+'&cutoff='+populationCutoff:''));if(!more)el('context-held-out').replaceChildren(node('option','No additional held-out population'));el('context-held-out').firstElementChild.value='';for(const v of data.items){const o=node('option',v.name+' · Version '+v.version+' · '+v.member_count+' papers');o.value=v.version_id;el('context-held-out').append(o);}populationPage=data.next_offset;populationCutoff=data.cutoff;el('context-more-populations').hidden=populationPage===null;}
el('context-builder').addEventListener('toggle',()=>{if(el('context-builder').open)guarded(()=>populations());});
el('context-more-populations').onclick=()=>guarded(()=>populations(true));el('context-find').onclick=()=>guarded(()=>findPapers(true));el('context-more-papers').onclick=()=>guarded(()=>findPapers(true,true));
el('context-form').addEventListener('input',invalidateContext);
el('context-form').onsubmit=event=>{event.preventDefault();guarded(async()=>{
  if(!target||!el('context-basis').value)throw Error('Explicitly select a target and representation.');await configuration();
  contextRequest={request_id:crypto.randomUUID().replaceAll('-',''),version_id:selected.version_id,actor:el('context-actor').value,created_at:config.suggested_time,config_event_id:config.config_event_id,target_paper_id:target,target_basis:el('context-basis').value,held_out_paper_ids:[],held_out_population_version:el('context-held-out').value||null,dependency_ids:[],
    strategy:{in_scope:Number(el('context-positive').value),out_of_scope:Number(el('context-negative').value),max_characters:Number(el('context-budget').value),max_per_reference:Number(el('context-per-paper').value),allow_truncation:el('context-truncate').checked,self_match:el('context-self').checked?'include_operational':'exclude'}};
  const candidate=contextRequest,data=await api('references/context_preview',contextRequest);if(contextRequest!==candidate)return;contextPreview=data;el('context-preview-status').textContent=data.selected_count+' selected references · '+data.text_characters+' text characters · '+(data.decision_count-data.selected_count)+' omissions. '+(data.independent_evaluation?'Self-match excluded.':'Operational self-match; not independent evaluation.');el('context-preview-input').textContent=JSON.stringify(data.input,null,2);el('context-preview').hidden=false;say('Context preview only; no context or scientific assessment saved.');
});};
el('context-freeze').onclick=()=>guarded(async()=>{if(!contextRequest||!contextPreview)return;const data=await api('references/context_commit',{...contextRequest,expected_preview_sha256:contextPreview.preview_sha256});invalidateContext();await contexts();await inspectContext(data.context_id);say('Exact selected context frozen. No model call, review observation or corpus decision created.');});
el('context-edit').onclick=invalidateContext;
async function contexts(more=false,back=false){const offset=back?Math.max(0,contextPage.current-20):more?contextPage.offset:0;const data=await api('references/contexts'+(more||back?'?offset='+offset+'&cutoff='+contextPage.cutoff:''));el('context-empty').textContent=data.items.length?'Saved local input manifests; no assessment engine has run.':'No saved selected contexts.';el('context-versions').replaceChildren(...data.items.map(v=>{const p=node('p',v.actor+' · '+v.created_at+' · '+v.selected_count+' selected references ');p.append(button('Inspect Selected Context',()=>inspectContext(v.context_id)));return p;}));contextPage={current:offset,offset:data.next_offset,cutoff:data.cutoff};el('context-more').hidden=data.next_offset===null;el('context-more-previous').hidden=!offset;}
async function inspectContext(cid,offset=0,verify=false){
  currentContext=cid;const data=await api('references/contexts/'+handle(cid)+(verify?'/verify':'')+'?offset='+offset);el('context-detail').hidden=false;el('context-status').textContent=data.selected_count+' selected references · '+data.text_characters+' characters · '+(data.strategy.self_match==='exclude'?'Self-match excluded':'Operational self-match')+(data.independent_evaluation?'':' · Not independent evaluation')+(verify?' · Integrity verified':'');
  const input=el('context-input');input.replaceChildren(node('h3','Target text'),node('pre',data.input.target.text));data.input.references.forEach((r,i)=>input.append(node('h3','Reference '+(i+1)+' · '+(r.label==='in_scope'?'Known in-scope':'Known out-of-scope')),node('pre',r.text)));for(const d of data.input.derived)input.append(node('h3','Unvalidated derived context'),node('pre',d.text));
  const {items,...header}=data;el('context-header').textContent=JSON.stringify(header,null,2);el('context-decisions').replaceChildren(...items.map((v,i)=>node('p','Assignment '+(offset+i+1)+' · '+v.decision+' · '+v.reason+(v.rank===null?'':' · Traversal rank '+v.rank)+(v.truncated?' · Explicitly truncated; '+v.omitted_characters+' characters omitted':''))));decisionStart=offset;decisionPage=data.next_offset;el('context-more-decisions').hidden=decisionPage===null;el('context-more-decisions-previous').hidden=!offset;if(!offset)el('context-detail-heading').focus();history.replaceState(null,'','/references#context-'+handle(cid));
}
el('context-more').onclick=()=>guarded(()=>contexts(true));el('context-more-decisions').onclick=()=>guarded(()=>inspectContext(currentContext,decisionPage));el('context-verify').onclick=()=>guarded(()=>inspectContext(currentContext,0,true));
window.addEventListener('beforeunload',event=>{if(staged.length){event.preventDefault();event.returnValue='';}});
previous('reference-more-versions','Previous Reference Versions',()=>versions(false,true));
previous('reference-more-members','Previous Reference Assignments',()=>members(Math.max(0,memberStart-20)));
previous('reference-more-changes','Previous Correction History',()=>changes(Math.max(0,changeStart-20)));
previous('context-more','Previous Saved Contexts',()=>contexts(false,true));
previous('context-more-decisions','Previous Selection Decisions',()=>inspectContext(currentContext,Math.max(0,decisionStart-20)));
(async()=>{renderStaged();await configuration();await versions();await contexts();const hash=location.hash.slice(1);if(/^[0-9a-f]{64}$/.test(hash))await inspectVersion('reference-version:'+hash);else if(/^context-[0-9a-f]{64}$/.test(hash))await inspectContext('reference-context:'+hash.slice(8));})().catch(fail);
