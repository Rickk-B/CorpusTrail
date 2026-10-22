'use strict';
// Operational only. Method-blind review never calls these endpoints.
const el=id=>document.getElementById(id), make=(tag,text)=>{const n=document.createElement(tag);n.textContent=text;return n;};
const token=document.querySelector('meta[name="corpustrail-session"]').content, schema='corpustrail-local-curation/v1';
const hash=id=>id.split(':').at(-1), uid=()=>crypto.randomUUID().replaceAll('-',''), json=x=>JSON.stringify(x,null,2);
const labels={include:'Likely include',exclude:'Likely exclude',uncertain:'Uncertain',failed:'Execution failed — not a judgment',not_assessed:'Not assessed',insufficient:'Insufficient evidence',unknown_sufficiency:'Sufficiency unknown',disagreement:'Disagreement',human_reviewed:'Human observation exists'};
let config, currentRun, runData, resultData, currentPaper, currentAudit, parentRun=null, planRequest=null, planPreview=null, savedPlan=null, auditRequest=null, auditPreview=null, correctionRequest=null, correctionPreview=null, resultOffset=0, locked=false, poll=null;
const cursors={}, selectedContexts=new Set(), replay=new Map();
const say=text=>{el('curation-message').textContent=text;};
function view(stage){
  el('curation-method-section').hidden=stage!=='overview';el('curation-run-list').hidden=stage!=='overview';
  el('curation-planner').hidden=!['overview','plan'].includes(stage)||!config.available||el('curation-engine').options.length===1;
  for(const name of ['run','paper','audit'])el('curation-'+name).hidden=stage!==name;
  el('curation-selected-run').hidden=!currentRun||stage==='run';el('curation-reassess').hidden=!currentRun;
}
async function api(path,body){
  const headers={'X-CorpusTrail-Session':token};if(body)Object.assign(headers,{'Content-Type':'application/json','X-CorpusTrail-CSRF':token});
  const r=await fetch('/api/v1/'+path,{method:body?'POST':'GET',headers,cache:'no-store',body:body?JSON.stringify({schema,...body}):undefined});
  const data=await r.json();if(!r.ok)throw new Error(data.error.message);return data;
}
// Preserve one exact command on uncertain responses. Deliberate form edits create
// a new identity; double clicks never create a second operation.
async function command(action,body){
  const key=action+JSON.stringify(body);if(!replay.has(key))replay.set(key,{request_id:uid(),...body});
  const value=await api('curation/'+action,replay.get(key));replay.delete(key);return value;
}
async function perform(work){if(locked)return;locked=true;document.querySelector('main').setAttribute('aria-busy','true');document.querySelectorAll('button').forEach(n=>{n.disabled=true;});
  try{await work();}catch(e){say('Not completed: '+e.message+' Saved scientific records remain intact; current form input is retained.');}
  finally{document.querySelectorAll('button').forEach(n=>{n.disabled=false;});el('curation-results-previous').disabled=resultOffset===0;el('curation-results-next').disabled=!resultData||resultData.next_offset===null;document.querySelector('main').removeAttribute('aria-busy');locked=false;}}
function button(text,work){const n=make('button',text);n.type='button';n.disabled=locked;n.onclick=()=>perform(work);return n;}
function details(parent,title,value){const n=make('details','');n.append(make('summary',title),make('pre',json(value)));parent.append(n);}
function counts(id,values){el(id).replaceChildren();for(const [k,v] of Object.entries(values))el(id).append(make('dt',labels[k]||k),make('dd',String(v)));}
function observation(card,value,prefix='Engine observation'){
  card.append(make('p',prefix+': '+(labels[value.outcome]||value.reason||'No judgment')+(value.evidence_sufficiency?' · evidence '+value.evidence_sufficiency:'')));
  if(value.score)card.append(make('p','Score '+value.score.value+' · '+value.score.score_type+' · '+value.score.meaning));
}
function query(options){return new URLSearchParams(Object.entries(options).filter(([,v])=>v!==null&&v!==undefined&&v!==''));}
function actor(){const value=el('curation-actor').value.trim();if(!value)throw new Error('Enter the explicit acting person in the plan form.');return value;}
function when(){return config.suggested_time;}
async function choices(kind,more=false){
  const c=cursors[kind]||{}, data=await api((kind==='population'?'populations/versions':kind==='context'?'references/contexts':'references/versions')+'?'+query({limit:20,offset:more?c.next:0,cutoff:more?c.cutoff:null}));
  const key=kind==='context'?'context_id':'version_id';
  if(kind==='context'){
    el('curation-contexts').replaceChildren();for(const item of data.items){const row=make('label','');row.className='choice';const box=document.createElement('input');box.type='checkbox';box.checked=selectedContexts.has(item[key]);box.onchange=()=>{if(box.checked)selectedContexts.add(item[key]);else selectedContexts.delete(item[key]);invalidatePlan();el('curation-context-count').textContent=selectedContexts.size+' exact contexts selected.';};row.append(box,make('span','For '+(item.target_evidence?.available?.metadata?.bibliography?.title||'Untitled target')+' · '+item.selected_count+' references · '+item.created_at));el('curation-contexts').append(row);}
  }else{
    const ids=kind==='population'?['curation-population']:['curation-reference','curation-correction-parent'];
    for(const id of ids){const select=el(id), value=select.value, kept=[...select.options].find(o=>o.value===value);select.replaceChildren(new Option('Choose a frozen '+kind+' version',''));if(kept&&value)select.add(new Option(kept.text,value));for(const item of data.items)if(item[key]!==value)select.add(new Option(item.name+' · v'+item.version+' · '+(item.member_count??item.counts?.assignment_count??'')+' entries',item[key]));select.value=value;}
  }
  cursors[kind]={next:data.next_offset,cutoff:data.cutoff};const name=kind==='context'?'curation-context-next':'curation-'+kind+'-next';el(name).hidden=data.next_offset===null;if(kind==='reference')el('curation-correction-parent-next').hidden=data.next_offset===null;
}
function selectExact(id,value,text){const s=el(id);if(![...s.options].some(n=>n.value===value))s.add(new Option(text||value,value));s.value=value;}
function invalidatePlan(){planRequest=null;planPreview=null;savedPlan=null;el('curation-plan-preview').hidden=true;el('curation-plan-saved').hidden=true;}
async function configuration(){
  config=await api('curation/configuration');el('curation-upgrade').hidden=config.available;
  el('curation-methods').replaceChildren();el('curation-engine').replaceChildren(new Option('Choose an available adapter',''));
  for(const method of config.methods){const row=make('article','');row.append(make('h3',method.label),make('p',method.available?'Available':'Unavailable'),make('p',method.notice));el('curation-methods').append(row);if(method.available&&method.id!=='manual')el('curation-engine').add(new Option(method.label,method.id+'|'+method.version));}
  el('curation-planner').hidden=!config.available||el('curation-engine').options.length===1;
  el('curation-reviewer-options').replaceChildren(...config.authorized_reviewers.map(v=>new Option(v,v)));
  el('curation-strata').replaceChildren(make('legend','Strata (used only for policy-stratified sampling)'));
  for(const name of [...config.primary_states,...config.overlays]){const row=make('label','');row.className='choice';const box=document.createElement('input');box.type='checkbox';box.value=name;box.checked=['exclude','uncertain','disagreement'].includes(name);row.append(box,make('span',labels[name]||name));el('curation-strata').append(row);}
  if(config.available){await choices('population');await choices('reference');await choices('context');await savedAudits();await historyPage();}
  await runs();
}
async function runs(more=false,comparison=false){
  const kind=comparison?'compare':'runs', c=cursors[kind]||{}, data=await api('curation/runs?'+query({offset:more?c.next:0,limit:20,cutoff:more?c.cutoff:null}));
  if(comparison){const s=el('curation-compare'),value=s.value,kept=[...s.options].find(o=>o.value===value);s.replaceChildren(new Option('No comparison',''));if(kept&&value)s.add(new Option(kept.text,value));for(const r of data.items)if(r.run_id!==currentRun&&r.population_version_id===runData.plan.population_version_id&&r.run_id!==value)s.add(new Option(r.name+' · '+r.run_id,r.run_id));s.value=value;}
  else{el('curation-runs').replaceChildren();if(!data.items.length)el('curation-runs').append(make('p','No assessment runs. Manual review remains available without an engine.'));for(const r of data.items){const card=make('article','');card.append(make('h3',r.name),make('p',r.engine.engine_id+' · '+r.created_at),button('Inspect Run Results',()=>openRun(r.run_id)));el('curation-runs').append(card);}}
  cursors[kind]={next:data.next_offset,cutoff:data.cutoff};el('curation-'+kind+'-next').hidden=data.next_offset===null;
}
async function openRun(id){clearTimeout(poll);currentRun=id;currentPaper=null;view('run');el('curation-compare').value='';resultOffset=0;await refreshRun();await runs(false,true);await results();el('curation-run-heading').focus({preventScroll:true});history.replaceState(null,'','/curation#'+hash(id));}
async function refreshRun(){
  runData=await api('curation/runs/'+hash(currentRun));el('curation-run-heading').textContent=runData.plan.name;
  el('curation-run-status').textContent='Execution state: '+runData.status+' · '+(runData.terminal?'Terminal':'Explicit continuation may remain')+(runData.local_worker_active?' · bounded local work active':'');
  el('curation-run-notice').textContent=runData.notice+(runData.diagnostic?' '+runData.diagnostic:'');
  el('curation-score-notice').textContent='Scores keep the engine’s declared semantics; they are not probabilities by assumption. Calibration: '+(runData.plan.calibration?json(runData.plan.calibration):'No calibration binding.');
  el('curation-run-details').textContent=json(runData);el('curation-execute').hidden=runData.terminal||!runData.engine_available||runData.local_worker_active;
  el('curation-stop').hidden=!runData.local_worker_active;el('curation-recover').hidden=runData.local_worker_active||runData.terminal;
  el('curation-validate').hidden=runData.validation_protocol.purpose==='operational';
  el('curation-validation-notice').textContent=runData.validation_protocol.purpose==='operational'?'Operational/reference agreement is not independent validation. No recall, precision or specificity is inferred from these examples.':'Frozen '+runData.validation_protocol.purpose+' roles. Metrics use explicit known-label denominators; sparse or synthetic sets and repeatedly corrected test sets do not establish fresh scientific performance.';
  await validations();
}
async function validations(more=false){const c=cursors.validations||{},data=await api('curation/runs/'+hash(currentRun)+'/validations?'+query({offset:more?c.next:0,limit:20,cutoff:more?c.cutoff:null}));el('curation-validations').replaceChildren();if(!data.items.length)el('curation-validations').append(make('p','No frozen-role validation records.'));for(const item of data.items){const row=make('article','');for(const name of ['known_inclusion_recall','known_exclusion_specificity','precision_on_known_binary_labels']){const v=item[name];row.append(make('p',name.replaceAll('_',' ')+': '+v.numerator+' / '+v.denominator+(v.value===null?' — not estimable':' = '+v.value)));}row.append(make('p',item.qualification));details(row,'Matrix, sufficiency overlays and exact source hashes',item);el('curation-validations').append(row);}cursors.validations={next:data.next_offset,cutoff:data.cutoff};el('curation-validations-next').hidden=data.next_offset===null;}
async function results(offset=0){
  const data=await api('curation/runs/'+hash(currentRun)+'/results?'+query({offset,limit:20,primary:el('curation-primary').value,overlay:el('curation-overlay').value,compare:el('curation-compare').value?hash(el('curation-compare').value):null,revision:offset?resultData?.revision:null}));resultData=data;resultOffset=offset;
  counts('curation-totals',data.primary);counts('curation-overlay-counts',data.overlays);el('curation-count-semantics').textContent=data.count_semantics;
  el('curation-result-count').textContent=data.filtered_total+' matching candidates of '+data.population_total+' frozen candidates. Showing '+data.items.length+' on this page.';
  el('curation-results').replaceChildren();for(const item of data.items){const card=make('article','');card.append(make('h3',item.publication.bibliography?.title||item.publication.title||'Untitled publication'),make('p',labels[item.primary_state]+' · '+(item.overlays.map(v=>labels[v]).join(' · ')||'No overlapping filter')),make('p','Current corpus decision: '+item.publication.membership.state+' · human authority: '+item.publication.membership.authority_state));if(item.observation)observation(card,item.observation);if(item.comparison)observation(card,item.comparison,'Comparison observation');card.append(button('Inspect Evidence, Context and Correction',()=>paper(item.paper_id)));el('curation-results').append(card);}
  if(!data.items.length)el('curation-results').append(make('p','No candidates match these filters. Clear filters to inspect the entire population.'));
  el('curation-results-previous').disabled=offset===0;el('curation-results-next').disabled=data.next_offset===null;
}
async function targetSegment(offset=0){const data=await api('curation/runs/'+hash(currentRun)+'/papers/'+hash(currentPaper)+'?'+query({section:'target',offset,limit:16000}));el('curation-paper-heading').textContent=data.frozen_title||'Frozen publication input';el('curation-paper-text').textContent=data.text;el('curation-paper-next').hidden=data.next_offset===null;el('curation-paper-next').dataset.offset=data.next_offset??'';}
async function inputReferences(offset=0){
  const data=await api('curation/runs/'+hash(currentRun)+'/papers/'+hash(currentPaper)+'?'+query({section:'references',offset,limit:10}));
  el('curation-input-references').replaceChildren();el('curation-reference-context-notice').textContent='Exact supplied references, including frozen labels and representation identities. Self-match / held-out rules and selection omissions remain in the plan/context provenance. '+(data.total??data.total_count??'')+' entries.';
  for(const [index,item] of data.items.entries()){const card=make('article','');card.append(make('h3','Reference '+(offset+index+1)+' · '+(item.label||'Frozen reference label')),button('Read Supplied Reference Passage',()=>referenceSegment(offset+index)));details(card,'Exact label, representation and assignment identities',item);el('curation-input-references').append(card);}
  el('curation-input-references-next').hidden=data.next_offset===null;el('curation-input-references-next').dataset.offset=data.next_offset??'';
}
async function referenceSegment(index,offset=0){const data=await api('curation/runs/'+hash(currentRun)+'/papers/'+hash(currentPaper)+'?'+query({section:'reference_text',index,offset,limit:16000}));el('curation-reference-text').textContent=data.text;el('curation-reference-text').hidden=false;const n=el('curation-reference-text-next');n.hidden=data.next_offset===null;n.dataset.index=index;n.dataset.offset=data.next_offset??'';}
async function paper(id,audit=null){
  currentPaper=id;view('paper');el('curation-paper').dataset.audit=audit||'';el('curation-paper-source').textContent='Exact frozen input from '+runData.plan.name+'. Full source identities remain available in provenance below.';
  el('curation-current-paper').href='/papers/'+hash(id);el('curation-reference-text').hidden=true;el('curation-reference-text-next').hidden=true;el('curation-correction-preview').hidden=true;el('curation-correction-result').textContent='';
  await targetSegment();await inputReferences();el('curation-paper-provenance').textContent=json(await api('curation/runs/'+hash(currentRun)+'/papers/'+hash(id)+'?section=provenance'));
  selectExact('curation-correction-parent',runData.plan.reference_version_id);el('curation-correction-label').value='';el('curation-correction-evidence').value='';el('curation-correction-attest').checked=false;el('curation-correction-rationale').value='';el('curation-paper-heading').focus({preventScroll:true});
}
async function savedAudits(more=false){
  const c=cursors.audits||{},data=await api('curation/audits?'+query({offset:more?c.next:0,limit:20,cutoff:more?c.cutoff:null}));el('curation-audits').replaceChildren();if(!data.items.length)el('curation-audits').append(make('p','No audit selections saved. Opening this page creates none.'));
  for(const a of data.items){const card=make('article','');card.append(make('h3',a.name),make('p',a.selected_count+' frozen papers · '+a.selection.mode+' · '+a.created_at),button('Inspect Frozen Audit',()=>openAudit(a.audit_id)));el('curation-audits').append(card);}cursors.audits={next:data.next_offset,cutoff:data.cutoff};el('curation-audits-next').hidden=data.next_offset===null;
}
async function openAudit(id,offset=0){
  currentAudit=id;const data=await api('curation/audits/'+hash(id)+'?'+query({offset,limit:20}));view('audit');el('curation-audit-heading').textContent=data.name;el('curation-audit-status').textContent=data.selected_count+' immutable selected candidates. '+data.qualification;el('curation-audit-details').textContent=json({...data,items:undefined});
  el('curation-audit-members').replaceChildren();for(const item of data.items){const card=make('article','');card.append(make('h3',item.publication.bibliography.title||'Untitled publication'),make('p','Current catalogue title · frozen selection: '+labels[item.primary_state]),button('Inspect Selected Assessment and Evidence',async()=>{await openRun(data.run_id);await paper(item.paper_id,id);}));details(card,'Frozen selection decisions',item);el('curation-audit-members').append(card);}
  el('curation-audit-members-next').hidden=data.next_offset===null;el('curation-audit-members-next').dataset.offset=data.next_offset??'';
  await auditHistory('sessions');await auditHistory('outcomes');el('curation-audit-heading').focus({preventScroll:true});
}
async function auditHistory(kind,more=false){
  const key='audit-'+kind,c=cursors[key]||{},data=await api('curation/audits/'+hash(currentAudit)+'/'+kind+'?'+query({offset:more?c.next:0,limit:20,cutoff:more?c.cutoff:null}));const name=kind==='sessions'?'curation-assisted-sessions':'curation-outcomes';el(name).replaceChildren();
  if(!data.items.length)el(name).append(make('p',kind==='sessions'?'No assisted sessions.':'No human audit outcomes or authorizations recorded.'));
  for(const item of data.items){const card=make('article','');if(kind==='sessions'){const a=make('a','Resume / inspect '+item.reviewer_id+' · '+item.lifecycle);a.href='/curation/review#'+hash(item.session_id);card.append(a);}else {card.append(make('h3',item.publication.bibliography.title||'Untitled publication'),make('p',(item.kind==='authorization'?'Explicit corpus authorization':'Saved human observation')+' · '+item.human_observation.state+' · '+item.actor),make('p',item.human_observation.rationale));}details(card,'Recorded provenance',item);el(name).append(card);}cursors[key]={next:data.next_offset,cutoff:data.cutoff};el(name+'-next').hidden=data.next_offset===null;
}
async function historyPage(more=false){const c=cursors.history||{},data=await api('curation/history?'+query({offset:more?c.next:0,limit:20,cutoff:more?c.cutoff:null}));el('curation-history').replaceChildren();if(!data.items.length)el('curation-history').append(make('p','No reference correction or explicit reassessment requests recorded.'));for(const item of data.items){const card=make('article','');card.append(make('h3',item.kind==='reference_correction'?'Human-attested successor reference':'Explicit reassessment request'),make('p',item.notice));details(card,'Exact immutable lineage',item);el('curation-history').append(card);}cursors.history={next:data.next_offset,cutoff:data.cutoff};el('curation-history-next').hidden=data.next_offset===null;}
el('curation-enable').onclick=()=>perform(async()=>{await command('upgrade',{confirm_backup:true,project_id:config.project_id,config_event_id:config.config_event_id});await configuration();say('Database backup created before additive curation upgrade.');});
el('curation-overview').onclick=()=>perform(async()=>{clearTimeout(poll);view('overview');await runs();await savedAudits();await historyPage();history.replaceState(null,'','/curation');});
el('curation-selected-run').onclick=()=>perform(async()=>{view('run');await refreshRun();await results();el('curation-run-heading').focus();});
for(const kind of ['population','reference','context'])el('curation-'+kind+'-next').onclick=()=>perform(()=>choices(kind,true));
el('curation-correction-parent-next').onclick=()=>perform(()=>choices('reference',true));
el('curation-plan-form').oninput=invalidatePlan;
el('curation-input-mode').onchange=()=>{el('curation-context-choice').hidden=el('curation-input-mode').value!=='bounded_context';invalidatePlan();};
el('curation-plan-form').onsubmit=event=>{event.preventDefault();perform(async()=>{const [engine_id,engine_version]=el('curation-engine').value.split('|');planRequest={request_id:uid(),name:el('curation-name').value,actor:actor(),created_at:when(),config_event_id:config.config_event_id,population_version_id:el('curation-population').value,reference_version_id:el('curation-reference').value,engine_id,engine_version,input_mode:el('curation-input-mode').value,context_ids:el('curation-input-mode').value==='bounded_context'?[...selectedContexts]:[],parent_run_id:parentRun};planPreview=await api('curation/plan_preview',planRequest);el('curation-plan-summary').textContent='Preview only: '+planPreview.candidate_count+' candidates; '+planPreview.eligible_reference_count+' eligible reference papers. Input: '+planPreview.input_mode+'; evidence: '+planPreview.evidence_basis+'. Policy: '+planPreview.policy.policy_id+'. Calibration: '+planPreview.calibration_state+'. Bounded work: at most '+planPreview.budgets.max_items_per_execution+' items per explicit execution. '+(parentRun?'Existing settings, policy and validation split are inherited; corrected validation labels are not fresh independent evaluation.':'');el('curation-plan-details').textContent=json(planPreview);el('curation-plan-preview').hidden=false;});};
el('curation-plan-commit').onclick=()=>perform(async()=>{savedPlan=await api('curation/plan_commit',{...planRequest,expected_preview_sha256:planPreview.preview_sha256});el('curation-plan-preview').hidden=true;el('curation-plan-saved').hidden=false;say('Plan frozen. No run or assessment has been executed.');});
el('curation-start').onclick=()=>perform(async()=>{const r=await command('start',{plan_id:savedPlan.plan_id,parent_run_id:parentRun,actor:actor(),created_at:when()});await runs();await openRun(r.run_id);await historyPage();say('New run explicitly requested. Execution requires a separate action.');});
el('curation-independent').onclick=()=>{parentRun=null;invalidatePlan();el('curation-parent').textContent='New independent plan.';el('curation-independent').hidden=true;};
el('curation-reassess').onclick=()=>perform(async()=>{parentRun=currentRun;invalidatePlan();view('plan');el('curation-parent').textContent='Explicit successor of '+runData.plan.name+'. Select the desired successor reference version. Existing policy/settings/validation split are inherited, not retrained. Nothing executes automatically.';selectExact('curation-population',runData.plan.population_version_id);selectExact('curation-reference',runData.plan.reference_version_id);selectExact('curation-engine',runData.plan.engine.engine_id+'|'+runData.plan.engine.version);el('curation-input-mode').value=runData.plan.input_mode;el('curation-input-mode').dispatchEvent(new Event('change'));el('curation-independent').hidden=false;el('curation-name').focus();});
function scheduleMonitor(){poll=setTimeout(()=>locked?scheduleMonitor():perform(monitor),500);}
async function monitor(){await refreshRun();if(runData.local_worker_active)scheduleMonitor();else await results();}
el('curation-execute').onclick=()=>perform(async()=>{await api('curation/execute',{run_id:currentRun,expected_revision:runData.revision});await monitor();});
el('curation-stop').onclick=()=>perform(async()=>{await api('curation/cancel',{run_id:currentRun});say('Stop requested. Current bounded work may finish; no automatic retry.');await refreshRun();});
el('curation-recover').onclick=()=>perform(async()=>{await api('curation/recover',{run_id:currentRun,expected_revision:runData.revision,actor:actor(),created_at:when()});await refreshRun();await results();say('Explicit recovery recorded. Inspect resulting failures before continuation.');});
el('curation-refresh').onclick=()=>perform(async()=>{await refreshRun();await results();});
el('curation-validate').onclick=()=>perform(async()=>{await api('curation/validate',{run_id:currentRun});await validations();say('Frozen-role validation recorded with explicit denominators. This does not publish membership or establish real-model performance.');});
el('curation-validations-next').onclick=()=>perform(()=>validations(true));
el('curation-results-form').onsubmit=e=>{e.preventDefault();perform(()=>results());};el('curation-compare').onchange=()=>perform(()=>results());
el('curation-results-next').onclick=()=>perform(()=>results(resultData.next_offset));el('curation-results-previous').onclick=()=>perform(()=>results(Math.max(0,resultOffset-20)));
el('curation-runs-next').onclick=()=>perform(()=>runs(true));el('curation-compare-next').onclick=()=>perform(()=>runs(true,true));
el('curation-audit-form').oninput=()=>{auditRequest=null;auditPreview=null;el('curation-audit-preview').hidden=true;};
el('curation-audit-form').onsubmit=e=>{e.preventDefault();perform(async()=>{auditRequest={request_id:uid(),name:el('curation-audit-name').value,actor:el('curation-audit-actor').value,created_at:when(),config_event_id:config.config_event_id,run_id:currentRun,compare_run_id:el('curation-compare').value||null,selection:{mode:el('curation-audit-mode').value,seed:Number(el('curation-audit-seed').value),size:Number(el('curation-audit-size').value),groups:[...el('curation-strata').querySelectorAll('input:checked')].map(n=>n.value),primary_filter:el('curation-primary').value,overlay_filter:el('curation-overlay').value}};auditPreview=await api('curation/audit_preview',auditRequest);el('curation-audit-preview-counts').textContent=auditPreview.selected_count+' distinct selected candidates; overlapping stratum selections: '+auditPreview.selection_overlap_count+'. No observation or membership was created.';el('curation-audit-preview-details').textContent=json(auditPreview);el('curation-audit-preview').hidden=false;});};
el('curation-audit-commit').onclick=()=>perform(async()=>{const r=await api('curation/audit_commit',{...auditRequest,expected_preview_sha256:auditPreview.preview_sha256});el('curation-audit-preview').hidden=true;await savedAudits();await openAudit(r.audit_id);say('Immutable audit selection saved. No human observation or corpus decision created.');});
el('curation-assisted-form').onsubmit=e=>{e.preventDefault();perform(async()=>{const r=await command('assisted_create',{audit_id:currentAudit,reviewer_id:el('curation-reviewer').value,config_event_id:config.config_event_id,confirm_assisted:el('curation-assisted-confirm').checked});location.assign('/curation/review#'+r.handle);});};
el('curation-audits-next').onclick=()=>perform(()=>savedAudits(true));el('curation-audit-members-next').onclick=()=>perform(()=>openAudit(currentAudit,Number(el('curation-audit-members-next').dataset.offset)));
el('curation-assisted-sessions-next').onclick=()=>perform(()=>auditHistory('sessions',true));el('curation-outcomes-next').onclick=()=>perform(()=>auditHistory('outcomes',true));el('curation-history-next').onclick=()=>perform(()=>historyPage(true));
el('curation-paper-next').onclick=()=>perform(()=>targetSegment(Number(el('curation-paper-next').dataset.offset)));el('curation-input-references-next').onclick=()=>perform(()=>inputReferences(Number(el('curation-input-references-next').dataset.offset)));el('curation-reference-text-next').onclick=()=>perform(()=>referenceSegment(Number(el('curation-reference-text-next').dataset.index),Number(el('curation-reference-text-next').dataset.offset)));
el('curation-correction-form').oninput=()=>{correctionRequest=null;correctionPreview=null;el('curation-correction-preview').hidden=true;};
el('curation-correction-form').onsubmit=e=>{e.preventDefault();perform(async()=>{correctionRequest={request_id:uid(),run_id:currentRun,audit_id:el('curation-paper').dataset.audit||null,paper_id:currentPaper,reference_version_id:el('curation-correction-parent').value,actor:el('curation-correction-actor').value,created_at:when(),config_event_id:config.config_event_id,label:el('curation-correction-label').value,evidence_used:[el('curation-correction-evidence').value],rationale:el('curation-correction-rationale').value,attest:el('curation-correction-attest').checked,replace_existing:el('curation-correction-attest').checked};correctionPreview=await api('curation/correction_preview',correctionRequest);const ref=correctionPreview.reference;el('curation-correction-summary').textContent='Proposed successor version '+ref.version+': '+ref.counts.in_scope+' Known in-scope; '+ref.counts.out_of_scope+' Known out-of-scope; '+ref.counts.conflicts+' conflicting papers. Your explicit '+correctionRequest.label+' label replaces active labels for this paper in the successor only. Earlier versions remain unchanged. No membership update or reassessment will occur.';el('curation-correction-details').textContent=json(correctionPreview);el('curation-correction-preview').hidden=false;});};
el('curation-correction-commit').onclick=()=>perform(async()=>{const r=await api('curation/correction_commit',{...correctionRequest,expected_preview_sha256:correctionPreview.preview_sha256});const name='Corrected reference · v'+correctionPreview.reference.version;el('curation-correction-preview').hidden=true;el('curation-correction-result').textContent=r.notice+' Successor reference version '+correctionPreview.reference.version+' saved.';selectExact('curation-reference',r.reference_version_id,name);selectExact('curation-correction-parent',r.reference_version_id,name);invalidatePlan();await historyPage();say('Human-attested successor saved. Prepare Explicit Reassessment, then freeze a plan and request a run if desired. No assessment executed.');});
window.addEventListener('pagehide',()=>clearTimeout(poll));
configuration().then(async()=>{if(/^[0-9a-f]{64}$/.test(location.hash.slice(1)))await openRun('assessment-run:'+location.hash.slice(1));}).catch(e=>say('Curation unavailable: '+e.message+' No operation was started.'));
