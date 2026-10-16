'use strict';
// Presentation only. Population selection, union and integrity are server-owned.
const field=id=>document.getElementById(id);
const populationToken=document.querySelector('meta[name="corpustrail-session"]').content;
const populationSchema='corpustrail-local-populations/v1';
const make=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
const message=value=>{field('population-message').textContent=value;};
let candidateRequest=null,approvedPreview=null,parentVersion=null,selectedVersion=null,busy=false;
let sourceOffset=null,sourceCutoff=null,versionOffset=null,versionCutoff=null,paperCursor=null;
const sources=new Map(),papers=new Set(),savedVersions=new Map();
let memberOffset=null,lineageOffset=null,issueOffset=null,provenanceLoaded=false;
let upgradeContext=null;
async function api(path,body=null){
  const headers={'X-CorpusTrail-Session':populationToken};
  if(body)Object.assign(headers,{'Content-Type':'application/json','X-CorpusTrail-CSRF':populationToken});
  const response=await fetch('/api/v1/'+path,{method:body?'POST':'GET',headers,cache:'no-store',body:body?JSON.stringify({schema:populationSchema,...body}):undefined});
  const value=await response.json();if(!response.ok)throw Error(value.error.message);return value;
}
function failure(error){message('Not completed: '+error.message+' Inspect saved versions before explicitly retrying. No automatic retry occurs.');}
function lock(value){busy=value;document.querySelectorAll('button').forEach(button=>{button.disabled=value;});}
function invalidate(){
  candidateRequest=null;approvedPreview=null;field('population-preview').hidden=true;
  field('population-accept-unresolved').checked=false;
}
function choice(container,label,spec){
  const row=make('label','');row.className='choice';const input=document.createElement('input');input.type='checkbox';
  input.onchange=()=>{const key=JSON.stringify(spec);if(input.checked)sources.set(key,spec);else sources.delete(key);invalidate();};
  row.append(input,make('span',label));container.append(row);
}
function counts(container,data){
  container.replaceChildren();
  for(const [label,value] of [[data.frozen?'Frozen canonical publications':'Canonical candidates in preview',data.member_count],['Source lineage records',data.lineage_count],
    ['Papers with multiple enrolled observations',data.overlapping_publications],['Unlinked records at source freezing',data.unresolved_count],['Population version',data.version]]){
    container.append(make('dt',label),make('dd',String(value)));
  }
}
async function configuration(more=false){
  const query=more?'?offset='+sourceOffset+'&cutoff='+sourceCutoff:'';
  const data=await api('populations/configuration'+query);
  if(!more)upgradeContext={project_id:data.project_id,config_event_id:data.config_event_id};
  field('population-upgrade').hidden=data.available;field('population-setup').hidden=!data.available;
  if(!more)field('population-discovery-sources').replaceChildren();
  for(const source of data.discovery_sources)choice(field('population-discovery-sources'),source.provider+' · '+source.query+' · '+source.created_at,
    {kind:'discovery',run_id:source.run_id});
  if(!more&&!data.discovery_sources.length)field('population-discovery-sources').append(make('p','No discovery sources with recorded outcomes yet.'));
  sourceOffset=data.next_offset;sourceCutoff=data.cutoff;field('population-more-sources').hidden=sourceOffset===null;
}
async function versions(more=false){
  const data=await api('populations/versions'+(more?'?offset='+versionOffset+'&cutoff='+versionCutoff:''));
  if(!more){field('population-versions').replaceChildren();savedVersions.clear();
    for(const [key,value] of sources)if(value.kind==='version')sources.delete(key);
  }
  field('population-list-status').textContent=data.total?data.total+' saved immutable versions. Select versions as union inputs, or inspect their frozen candidates.':'No saved population versions. Nothing has been created by opening this page.';
  for(const version of data.items){
    savedVersions.set(version.version_id,version);
    const card=make('article','');card.append(make('h3',version.name+' · Version '+version.version+' · Frozen'),
      make('p',version.member_count+' canonical publications · '+version.lineage_count+' lineage records · Created by '+version.actor),make('p',version.created_at));
    choice(card,'Use '+version.name+' · Version '+version.version+' in a combination',{kind:'version',version_id:version.version_id});
    const actions=make('div','');actions.className='pager';
    const inspect=make('button','Inspect Frozen Version');inspect.type='button';inspect.onclick=()=>inspectVersion(version.version_id).catch(failure);
    const successor=make('button','Create Successor Version');successor.type='button';successor.onclick=()=>{
      parentVersion=version.version_id;field('population-name').value=version.name;
      field('population-parent').textContent='New successor of '+version.name+' · Version '+version.version+'. Choose the complete source selection below. Earlier versions will not change.';
      field('population-parent').hidden=false;field('population-new-family').hidden=false;invalidate();field('population-name').focus();
    };actions.append(inspect,successor);card.append(actions);field('population-versions').append(card);
  }
  versionOffset=data.next_offset;versionCutoff=data.cutoff;field('population-more-versions').hidden=versionOffset===null;
}
async function findPapers(more=false){
  const q=field('population-search').value.trim();
  const data=await api('papers?'+new URLSearchParams({q,limit:20,...(more?{cursor:paperCursor}:{})}));
  if(!more)field('population-paper-choices').replaceChildren();
  for(const item of data.items){
    const row=make('label','');row.className='choice';const input=document.createElement('input');input.type='checkbox';input.checked=papers.has(item.paper_id||'ct-paper:'+item.handle);
    input.onchange=()=>{const id='ct-paper:'+item.handle;if(input.checked)papers.add(id);else papers.delete(id);invalidate();
      field('population-selection-count').textContent=papers.size+' individual publications selected.';};
    row.append(input,make('span',item.bibliography.title||'Untitled publication'));field('population-paper-choices').append(row);
  }
  if(!more&&!data.items.length)field('population-paper-choices').append(make('p','No collected publications match this query.'));
  paperCursor=data.next_cursor;field('population-more-papers').hidden=paperCursor===null;
}
function requestFields(){
  const selected=[...sources.values()];
  for(const kind of ['all','corpus','awaiting'])if(field('population-'+kind).checked)selected.push({kind});
  if(papers.size)selected.push({kind:'selection',paper_ids:[...papers]});
  return {name:field('population-name').value,actor:field('population-actor').value,sources:selected,parent:parentVersion};
}
field('population-form').addEventListener('input',invalidate);
field('population-form').onsubmit=async event=>{
  event.preventDefault();if(busy)return;lock(true);
  try{
    candidateRequest={request_id:crypto.randomUUID().replaceAll('-',''),...requestFields()};
    const request=candidateRequest,data=await api('populations/preview',request);
    // An edit may invalidate the selection while its read-only preview is in flight.
    // Never redisplay or approve that older response over the edited selection.
    if(candidateRequest!==request)return;
    approvedPreview=data.population;
    counts(field('population-preview-counts'),approvedPreview);field('population-preview').hidden=false;
    field('population-unresolved-label').hidden=!approvedPreview.unresolved_count;
    field('population-preview-heading').focus();message('Preview only. No population, review or corpus decision has been created.');
  }catch(error){failure(error);}finally{lock(false);}
};
field('population-freeze').onclick=async()=>{
  if(busy||!approvedPreview||!candidateRequest)return;lock(true);
  try{
    const data=await api('populations/create',{...candidateRequest,expected_preview_sha256:approvedPreview.preview_sha256,
      accept_unresolved:field('population-accept-unresolved').checked});
    invalidate();await versions();await inspectVersion(data.population.version_id);
    message('Candidate population frozen. No review observations or corpus-membership decisions were created.');
  }catch(error){failure(error);}finally{lock(false);}
};
field('population-edit').onclick=()=>{field('population-preview').hidden=true;approvedPreview=null;field('population-name').focus();};
field('population-new-family').onclick=()=>{parentVersion=null;field('population-parent').hidden=true;field('population-new-family').hidden=true;invalidate();};
async function inspectVersion(vid){
  selectedVersion=vid;const handle=vid.split(':')[1];const data=await api('populations/versions/'+handle);
  field('population-detail').hidden=false;field('population-detail-heading').textContent=data.name+' · Version '+data.version;
  field('population-detail-status').textContent='Frozen · Created by '+data.actor+' · '+data.created_at;
  counts(field('population-detail-counts'),data);field('population-review').hidden=!data.member_count;
  field('population-detail-sources').replaceChildren();
  for(const source of data.sources){
    const labels={all:'All collected canonical publications at freezing',corpus:'Authoritative corpus members at freezing',awaiting:'Publications awaiting a decision at freezing'};
    const label=source.kind==='version'?source.name+' · Frozen version '+source.version:source.kind==='discovery'?source.provider+' · '+source.query:
      source.kind==='selection'?source.selected_count+' explicitly selected publications':source.kind==='import_interface'?'Adapter-facing source interface · '+source.interface.adapter_id+' '+source.interface.adapter_version:labels[source.kind];
    field('population-detail-sources').append(make('li',label));
  }
  field('population-review').href='/review#population-'+handle;
  field('population-header').textContent=JSON.stringify(data,null,2);field('population-provenance').open=false;provenanceLoaded=false;
  field('population-verify-result').textContent='';await memberPage(0);field('population-detail-heading').focus();
  history.replaceState(null,'','/populations#'+handle);
}
async function memberPage(offset){
  const data=await api('populations/versions/'+selectedVersion.split(':')[1]+'/members?offset='+offset);
  if(!offset)field('population-members').replaceChildren();
  for(const item of data.items){const p=make('p','');const link=make('a',item.title||'Untitled publication');link.href='/papers/'+item.handle;
    p.append(link,make('span',' · '+item.lineage_count+' frozen lineage records'));field('population-members').append(p);}
  if(!data.total)field('population-members').append(make('p','This frozen version contains no canonical publications.'));
  memberOffset=data.next_offset;field('population-more-members').hidden=memberOffset===null;
}
async function lineagePage(section,offset){
  const data=await api('populations/versions/'+selectedVersion.split(':')[1]+'/'+section+'?offset='+offset);
  const box=field('population-'+section);if(!offset)box.replaceChildren();
  for(const item of data.items)box.append(make('pre',JSON.stringify(item,null,2)));
  if(section==='lineage')lineageOffset=data.next_offset;else issueOffset=data.next_offset;
  field('population-more-'+section).hidden=data.next_offset===null;
}
field('population-provenance').addEventListener('toggle',async()=>{
  if(!field('population-provenance').open||provenanceLoaded)return;
  try{await lineagePage('lineage',0);await lineagePage('issues',0);provenanceLoaded=true;}catch(error){failure(error);}
});
field('population-verify').onclick=async()=>{if(busy)return;lock(true);try{await api('populations/verify',{handle:selectedVersion.split(':')[1]});field('population-verify-result').textContent='Stored population integrity verified. This is not a corpus-membership or evidence-trust decision.';}catch(error){failure(error);}finally{lock(false);}};
field('population-enable').onclick=async()=>{if(busy)return;lock(true);try{await api('populations/upgrade',{request_id:crypto.randomUUID().replaceAll('-',''),confirm_backup:true,...upgradeContext});await configuration();await versions();message('Population storage enabled with a project-local backup. Existing research records are preserved.');}catch(error){failure(error);}finally{lock(false);}};
field('population-refresh').onclick=()=>{invalidate();versions().catch(failure);};
field('population-more-versions').onclick=()=>versions(true).catch(failure);
field('population-more-sources').onclick=()=>configuration(true).catch(failure);
field('population-find').onclick=()=>findPapers().catch(failure);field('population-more-papers').onclick=()=>findPapers(true).catch(failure);
field('population-more-members').onclick=()=>memberPage(memberOffset).catch(failure);
field('population-more-lineage').onclick=()=>lineagePage('lineage',lineageOffset).catch(failure);
field('population-more-issues').onclick=()=>lineagePage('issues',issueOffset).catch(failure);
(async()=>{await configuration();await versions();const handle=location.hash.slice(1);if(/^[0-9a-f]{64}$/.test(handle))await inspectVersion('population-version:'+handle);})().catch(failure);
