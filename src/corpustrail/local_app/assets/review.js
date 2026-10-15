'use strict';
// Frozen, allowlisted review DTOs only; never use the operational paper API here.
const el = id => document.getElementById(id);
const token = document.querySelector('meta[name="corpustrail-session"]').content;
const schema = 'corpustrail-guided-review/v1';
const names = {included:'Include', excluded:'Exclude', insufficient_evidence:'Insufficient evidence', undecided:'Undecided',
  not_reviewed:'Awaiting a corpus decision', unresolved:'Unresolved',
  metadata:'Bibliographic metadata', abstract:'Abstract', sections:'Verified structured text — selected sections', full_document:'Verified structured text — full document', none:'No evidence reviewed'};
let setup, state, dirty = false, busy = false, timer, queue = Promise.resolve(), uncertain = null, pendingCreate = null, summaryOffset = null, previewVisible = false;
let savedPopulationOffset=null,savedPopulationCutoff=null;
const say = value => { el('review-message').textContent = value; };
const node = (tag, text) => { const n = document.createElement(tag); n.textContent = text; return n; };
function enqueue(work) { const next = queue.catch(() => {}).then(work); queue = next.catch(() => {}); return next; }
async function api(path, body) {
  const headers = {'X-CorpusTrail-Session':token};
  if (body) Object.assign(headers, {'Content-Type':'application/json','X-CorpusTrail-CSRF':token});
  const response = await fetch('/api/v1/review/' + path, {method:body?'POST':'GET', headers, cache:'no-store', body:body?JSON.stringify(body):undefined});
  const data = await response.json();
  if (!response.ok) { const error = new Error(data.error.message); error.knownResponse = true; throw error; }
  return data;
}
function draft() {
  const outcome = document.querySelector('input[name="assessment"]:checked')?.value || null;
  return {sufficiency:outcome==='insufficient_evidence'?'insufficient':outcome?'sufficient':null,
    decision:outcome==='included'||outcome==='excluded'?outcome:null, review_extent:el('review-extent').value||null,
    rationale:el('review-rationale').value, location:null};
}
function setDraft(value) {
  const outcome = value.sufficiency==='insufficient'?'insufficient_evidence':value.decision;
  document.querySelectorAll('input[name="assessment"]').forEach(n => { n.checked=n.value===outcome; });
  el('review-extent').value = value.review_extent || ''; el('review-rationale').value = value.rationale;
}
function controls() {
  const closed = !state || state.legacy || state.stale || state.lifecycle!=='active';
  el('assessment-fields').disabled = closed || busy;
  for (const id of ['review-save-next','review-skip','review-next','review-previous','review-finish','review-prepare-publication','review-publish','review-open-document']) el(id).disabled=busy||state?.stale||state?.legacy;
  if (state) {
    el('review-previous').disabled ||= closed || state.number===1;
    el('review-next').disabled ||= closed || state.number===state.total;
    el('review-skip').disabled ||= closed;
    el('review-save-next').disabled ||= closed;
  }
}
async function command(action, value = null) {
  let body = {schema,handle:state.handle,command_id:crypto.randomUUID().replaceAll('-',''),expected_revision:state.revision,action,value};
  if (uncertain && uncertain.handle===body.handle && uncertain.action===action && JSON.stringify(uncertain.value)===JSON.stringify(value)) body=uncertain;
  try {
    const data = await api('command', body); state.revision=data.revision; uncertain=null; return data;
  } catch (error) {
    if (!error.knownResponse) uncertain=body;
    throw error;
  }
}
function failure(error) {
  say('Not saved: '+error.message+' Your current input is retained. Inspect the session before retrying.');
  el('review-save-state').textContent='Needs attention — current input retained';
  el('review-recover').hidden=!state;
}
async function flush() {
  clearTimeout(timer);
  return enqueue(async () => {
    if (!dirty) return;
    const value=draft(); el('review-save-state').textContent='Saving draft…';
    await command('draft',value);
    dirty=JSON.stringify(value)!==JSON.stringify(draft());
    el('review-save-state').textContent=dirty?'Unsaved edits':'Draft saved — no observation recorded';
  });
}
async function perform(action,value=null) {
  if (busy) return;
  busy=true;controls();
  try {
    await flush();
    const result=await enqueue(() => command(action, action==='save_next'?draft():value));
    if (action==='finish') {
      if (result.result.status!=='completed') throw new Error('Completion was not confirmed. Reload the saved session.');
      // Completion is acknowledged before navigation; no automatic publication.
      busy=false;dirty=false;location.assign('/dashboard#review-completed-'+state.handle);return;
    }
    await load(state.handle,{preview:action==='prepare_publication'});
    if (action==='save_next') say('Human observation saved. Corpus membership has not changed.');
    if (action==='skip') say('Skipped for now. No scientific judgment or corpus decision was created.');
    if (action==='publish') say('These confirmed decisions updated broad-corpus membership.');
  } catch(error) { failure(error); } finally { busy=false;controls(); }
}
async function overview() {
  setup=await api('configuration');
  el('review-overview').hidden=false; el('review-workspace').hidden=true;
  el('review-create').hidden=!setup.populations.some(p=>p.count)||!setup.definition;
  el('review-empty').textContent=!setup.definition?'Set an explicit broad-corpus definition in Project Settings before starting Guided Review.':
    setup.populations[0].count?'Choose a reviewing identity and a fixed publication set.':'No publications to review yet. Use Discovery or return to Corpus.';
  const select=el('review-population');select.replaceChildren(new Option('Choose a population',''));
  setup.populations.forEach(p=>{ const option=new Option(p.label+' ('+p.count+')',p.selection);option.disabled=!p.count;select.add(option); });
  await savedPopulations();
  el('reviewer-options').replaceChildren(...setup.authorized_reviewers.map(x=>new Option(x,x)));
  el('review-sessions').replaceChildren();
  await sessions(setup); el('review-more-sessions').dataset.offset=setup.next_offset??'';
  el('review-more-sessions').hidden=setup.next_offset===null;
  history.replaceState(null,'','/review'); state=null;dirty=false;
}
async function sessions(data) {
  if (!data.total_sessions) el('review-sessions').append(node('p','No review sessions have been created.'));
  for (const session of data.sessions) {
    const card=node('article','');card.append(node('h3',session.reviewer+' · '+(session.published?'Published':session.status)),
      node('p',session.saved+' saved observations · '+session.total+' frozen publications'),node('p',session.created_at));
    const button=node('button',session.legacy?'Inspect legacy session':session.status==='completed'?'View Review Summary':'Open review session');
    button.onclick=()=>load(session.handle).catch(failure);card.append(button);el('review-sessions').append(card);
  }
}
async function load(handle,{preview=false}={}) {
  const data=await api('sessions/'+handle); state=data;dirty=false;clearTimeout(timer);
  previewVisible=preview;
  el('review-recover').hidden=true;el('review-recovery').hidden=true;
  el('review-overview').hidden=true;el('review-workspace').hidden=false;el('review-summary').hidden=true;
  el('review-paper').hidden=false;
  el('review-progress').textContent='Paper '+data.number+' of '+data.total+' · '+data.recorded_count+' with saved observations';
  el('review-identity').textContent='Reviewer: '+data.reviewer+' · '+(data.can_publish?'Configured corpus-publication authority':'No corpus-publication authority');
  el('review-population-version').textContent=data.candidate_population?'Frozen candidate population · Version '+data.candidate_population.version+'. Exact version identity is available in session provenance.':'Session-local frozen candidate set; no saved population version was selected.';
  el('review-mode-notice').textContent=data.mode==='method-blind'?'Method-blind snapshot: discovery methods and earlier judgments are omitted. Corpus and other operational pages are not blinded.':'Operational review: frozen source attribution is available below.';
  el('review-definition').textContent=data.question;el('review-stale').hidden=!data.stale;
  el('review-paper-title').textContent=data.title||'Title not available';
  el('review-bibliography').textContent=[data.authors.join(', ')||'Authors not available',data.year,data.source].filter(Boolean).join(' · ');
  el('review-identifiers').textContent=data.identifiers.map(x=>x.scheme.toUpperCase()+': '+x.value).join(' · ');
  el('review-evidence-status').textContent=(data.abstract?'Abstract available':'No abstract available')+' · '+(data.document_available?'Verified structured text available':'No verified structured text in this snapshot')+
    (data.pending_documents?' · Pending documents: '+data.pending_documents:'')+(data.evidence.invalid_or_mismatched?' · Invalid/mismatched documents: '+data.evidence.invalid_or_mismatched:'');
  el('review-abstract-source').textContent=data.abstract?(data.evidence.abstract_origin==='verified_document'?'Abstract derived from a verified document.':'Bibliographic/discovery metadata abstract — not verified full text.') : 'Review remains possible using metadata; missing evidence is not exclusion.';
  el('review-abstract').textContent=data.abstract||'';
  el('review-document').hidden=true;el('review-document-next').hidden=true;el('review-document-position').textContent='';
  el('review-open-document').hidden=!data.document_available||data.lifecycle==='completed'&&!data.document_opened;
  el('review-source-details').hidden=data.mode!=='operational';el('review-sources').textContent=data.source_provenance?JSON.stringify(data.source_provenance,null,2):'';
  const extent=el('review-extent'),placeholder=new Option('Choose review extent','');placeholder.disabled=true;
  extent.replaceChildren(placeholder);
  for (const option of ['none',...data.review_options]) extent.add(new Option(names[option],option));
  setDraft(data.review);el('review-save-state').textContent=data.recorded?'Previously saved observation; changes require an explicit save.':'Drafts are not recorded observations.';
  el('review-save-next').textContent=data.number===data.total?'Save assessment':'Save & Next';
  const completed=data.lifecycle==='completed';
  el('legacy-review-notice').hidden=!data.legacy;el('assessment-form').hidden=data.legacy||completed;
  el('review-completion').hidden=data.legacy;
  el('review-show-summary').hidden=data.legacy||completed;el('review-finish').hidden=data.legacy||completed;
  el('review-completion-heading').textContent=completed?'Review completed — read only':'Review completion';
  el('review-readonly-help').hidden=!completed;
  el('review-completion-status').textContent=data.published?'Saved observations are preserved. Authoritative corpus updates have been published separately.':completed?'Saved observations are preserved. Unassessed papers remain undecided. Completing this session did not change corpus membership.':'Finish Review completes this session and preserves saved observations. Unassessed papers and incomplete or changed-unsaved drafts remain undecided. Corpus membership will not change.';
  el('review-technical').textContent=JSON.stringify({session:handle,revision:data.revision,population_sha256:data.population_sha256,evidence_snapshot_sha256:data.evidence_snapshot_sha256,candidate_population:data.candidate_population},null,2);
  history.replaceState(null,'','/review#'+handle);controls();
  if (completed&&!data.legacy) await summary();
}
async function summary(more=false) {
  const preview=previewVisible&&state.can_publish&&state.lifecycle==='completed'&&!state.published&&Boolean(state.publication_plan_sha256);
  if (!more) {
    el('review-summary-papers').replaceChildren();summaryOffset=0;
    const values=state.summary;const list=el('review-summary-counts');list.replaceChildren();
    for (const [label,value] of [[preview?'Proposed included publications':'Include',values.counts.included],[preview?'Proposed excluded publications':'Exclude',values.counts.excluded],['Insufficient evidence',values.counts.insufficient_evidence],[preview?'Undecided — not published':'Undecided in completion',values.undecided],['Changed unsaved drafts',values.changed_drafts],['Incomplete drafts',values.incomplete_drafts]]) list.append(node('dt',label),node('dd',String(value)));
  }
  const page=await api('sessions/'+state.handle+'/summary?offset='+summaryOffset);
  for (const paper of page.items) {
    const row=node('li','');row.append(node('h3',paper.title||'Untitled publication'),node('p',(names[paper.state]||paper.state)+(paper.changed_draft?' — changed draft not selected':'')+(preview&&paper.current_membership?' · Corpus state at confirmation preview: '+(names[paper.current_membership]||paper.current_membership):'')));
    if (paper.observation_event_id) {
      row.append(node('p','Evidence reviewed: '+(names[paper.review_extent]||paper.review_extent)),node('p',paper.rationale));
      const details=node('details','');details.append(node('summary','Saved observation provenance'),node('p','Observation: '+paper.observation_event_id));
      if (paper.publication_link) details.append(node('p','Authoritative decision: '+paper.publication_link.authority_event_id));
      row.append(details);
    } else row.append(node('p','No saved judgment selected for publication. This paper remains undecided in this completion.'));
    el('review-summary-papers').append(row);
  }
  summaryOffset=page.next_offset;el('review-summary-more').hidden=summaryOffset===null;
  el('review-summary').hidden=false;el('review-return').hidden=state.lifecycle!=='active';
  el('review-summary-heading').textContent=preview?'Proposed corpus updates':'Review summary';
  el('review-authority-status').textContent=state.published?'Authoritative publication completed.':!state.can_publish?'This reviewer is not authorized to publish corpus membership. Completed observations remain available.':'Publication requires a separate preview and explicit confirmation. No updates have been published by this session.';
  el('review-prepare-publication').hidden=state.lifecycle!=='completed'||!state.can_publish||state.published||!state.summary.selected_observations||preview;
  el('review-publication').hidden=!preview;
  el('review-publication-notice').textContent='Acting reviewer: '+state.reviewer+'. Policy: '+state.policy_id+'. Definition: '+state.question+' This operational, non-blinded confirmation covers all '+state.summary.selected_observations+' selected saved judgments across the summary pages. '+state.summary.undecided+' undecided publications remain unpublished.';
  el('review-paper').hidden=true;el('assessment-form').hidden=true;
  if (!more) el('review-summary-heading').focus({preventScroll:true});
}
el('review-create').onsubmit=async event=>{
  event.preventDefault();if(busy)return;busy=true;el('start-review').disabled=true;
  try {
    const p=setup.populations.find(x=>x.selection===el('review-population').value);
    const fields={schema,reviewer_id:el('reviewer').value,selection:p.selection,population_sha256:p.sha256,config_event_id:setup.config_event_id,mode:el('review-mode').value};
    if (!pendingCreate || JSON.stringify(pendingCreate.fields)!==JSON.stringify(fields)) pendingCreate={fields,command_id:crypto.randomUUID().replaceAll('-','')};
    const data=await api('create',{...fields,command_id:pendingCreate.command_id});pendingCreate=null;
    await load(data.handle);say('Frozen session created. No assessment or membership decision has been recorded.');
  }catch(error){failure(error);}finally{busy=false;el('start-review').disabled=false;controls();}
};
el('assessment-form').oninput=()=>{dirty=true;el('review-save-state').textContent='Unsaved edits';clearTimeout(timer);timer=setTimeout(()=>flush().catch(failure),500);};
el('assessment-form').onsubmit=event=>{event.preventDefault();perform('save_next');};
el('review-previous').onclick=()=>perform('navigate','previous');el('review-next').onclick=()=>perform('navigate','next');el('review-skip').onclick=()=>perform('skip');
el('review-show-summary').onclick=async()=>{try{await flush();state=await api('sessions/'+state.handle);await summary();}catch(e){failure(e);}};
el('review-summary-more').onclick=()=>summary(true).catch(failure);
el('review-return').onclick=()=>{el('review-summary').hidden=true;el('review-paper').hidden=false;el('assessment-form').hidden=false;el('review-paper-title').focus({preventScroll:true});};
el('review-finish').onclick=()=>perform('finish',{preserve_undecided:true});
el('review-prepare-publication').onclick=()=>perform('prepare_publication');
el('review-publish').onclick=()=>perform('publish',{plan_sha256:state.publication_plan_sha256,confirm_authority:true});
el('review-back-summary').onclick=()=>{previewVisible=false;summary().catch(failure);};
async function documentSegment(offset=0) {
  const data=await api('sessions/'+state.handle+'/document?offset='+offset);
  el('review-document').textContent=data.text;el('review-document').hidden=false;
  el('review-document-position').textContent='Characters '+(offset+1)+'–'+(offset+data.text.length)+' of '+data.total_characters;
  el('review-document-next').hidden=data.next_offset===null;el('review-document-next').dataset.offset=data.next_offset??'';
}
el('review-open-document').onclick=async()=>{try{if(!state.document_opened)await perform('open');if(state.document_opened)await documentSegment();}catch(e){failure(e);}};
el('review-document-next').onclick=()=>documentSegment(Number(el('review-document-next').dataset.offset)).catch(failure);
el('review-overview-button').onclick=()=>flush().then(overview).catch(failure);
el('review-more-sessions').onclick=async()=>{try{const data=await api('configuration?offset='+el('review-more-sessions').dataset.offset);await sessions(data);el('review-more-sessions').dataset.offset=data.next_offset??'';el('review-more-sessions').hidden=data.next_offset===null;}catch(e){failure(e);}};
function addSavedPopulation(version){
  if(setup.populations.some(p=>p.selection===version.version_id))return;
  const p={selection:version.version_id,label:version.name+' · Frozen version '+version.version,count:version.member_count,sha256:version.members_sha256};
  setup.populations.push(p);const option=new Option(p.label+' ('+p.count+')',p.selection);option.disabled=!p.count;el('review-population').add(option);
}
async function populationRead(path){
  const response=await fetch('/api/v1/populations/'+path,{headers:{'X-CorpusTrail-Session':token},cache:'no-store'});
  const value=await response.json();if(!response.ok)throw Error(value.error.message);return value;
}
async function savedPopulations(more=false){
  const data=await populationRead('versions'+(more?'?offset='+savedPopulationOffset+'&cutoff='+savedPopulationCutoff:''));
  data.items.forEach(addSavedPopulation);savedPopulationOffset=data.next_offset;savedPopulationCutoff=data.cutoff;
  el('review-more-populations').hidden=savedPopulationOffset===null;
}
el('review-more-populations').onclick=()=>savedPopulations(true).catch(failure);
el('review-recover').onclick=async()=>{
  const previous=state.paper_id,retained=draft();clearTimeout(timer);
  try {
    await queue;await load(state.handle);uncertain=null;el('review-recover').hidden=true;
    if (previous===state.paper_id && state.lifecycle==='active' && !state.stale) {
      setDraft(retained);dirty=true;el('review-save-state').textContent='Your edits are retained. Inspect them before an explicit save.';
    } else {
      el('review-recovery').hidden=false;
      el('review-recovered-note').value=(names[retained.decision]||names[retained.sufficiency==='insufficient'?'insufficient_evidence':'']||'No assessment')+' · '+(names[retained.review_extent]||'No extent selected')+'\n'+retained.rationale;
      say('The session moved or became read-only. Earlier input is retained below, not applied to another publication.');
    }
  }catch(error){failure(error);}
};
async function provenance(offset=0) {
  const value=await api('sessions/'+state.handle+'/summary?offset='+offset);
  el('review-technical').textContent=JSON.stringify(value,null,2);
  el('review-provenance-more').hidden=value.next_offset===null;el('review-provenance-more').dataset.offset=value.next_offset??'';
}
el('review-inspect-provenance').onclick=()=>provenance().catch(failure);
el('review-provenance-more').onclick=()=>provenance(Number(el('review-provenance-more').dataset.offset)).catch(failure);
document.querySelectorAll('nav a,header a,#review-summary a').forEach(link=>link.addEventListener('click',async event=>{
  if (!dirty) return;event.preventDefault();try{await flush();location.assign(link.href);}catch(e){failure(e);}
}));
window.addEventListener('beforeunload',event=>{if(dirty||busy){event.preventDefault();event.returnValue='Unsaved review input';}});
(async()=>{const handle=location.hash.slice(1);if(/^[0-9a-f]{64}$/.test(handle))await load(handle);else{
  await overview();if(/^population-[0-9a-f]{64}$/.test(handle)){
    const version=await populationRead('versions/'+handle.slice(11));addSavedPopulation(version);
    el('review-population').value=version.version_id;say('Frozen population selected. Choose your reviewing identity and start explicitly.');
  }
}})().catch(failure);
