'use strict';
// Guided forms only. Scientific validation and writes belong to application services.
const get = id => document.getElementById(id);
const sessionToken = document.querySelector('meta[name="corpustrail-session"]').content;
const formSchema = 'corpustrail-project-form/v1';
const make = (tag, value = '') => { const el = document.createElement(tag); el.textContent = value; return el; };
let entryData, settingsData, step = 0, requestId = null, busy = false;
const editing = location.pathname === '/settings';
function message(value) { get('message').textContent = value; }
async function request(path, body, schema = formSchema) {
  const options = {headers: {'X-CorpusTrail-Session': sessionToken}, cache: 'no-store'};
  if (body !== undefined) {
    options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
    options.headers['X-CorpusTrail-CSRF'] = sessionToken;
    options.body = JSON.stringify({schema, ...body});
  }
  const response = await fetch('/api/v1/' + path, options);
  const value = await response.json();
  if (!response.ok) throw new Error(value.error.message);
  return value;
}
function selected(kind) {
  return [...document.querySelectorAll('input[data-kind="' + kind + '"]')].filter(el => el.checked).map(el => el.value);
}
function lines(id) { return get(id).value.split('\n').map(x => x.trim()).filter(Boolean); }
function fields() {
  const before = settingsData ? settingsData.fields : {providers: [], search: [], resolvers: []};
  const chosenProviders = selected('provider');
  const installed = adapter => entryData.capabilities.providers.some(a => a.id === adapter);
  const providers = before.providers.filter(p => !installed(p.adapter) || chosenProviders.includes(p.adapter)).map(p => {
    if (!installed(p.adapter)) return p;
    const control = get('credential-' + p.adapter);
    if (!control) return p;
    const shown = before.providers.find(old => old.adapter === p.adapter)?.credential_env || '';
    return control.value.trim() === shown ? p : {...p, credential_env: control.value.trim() || null};
  });
  providers.push(...chosenProviders.filter(id => !before.providers.some(p => p.adapter === id)).map(id =>
    ({id, adapter: id, credential_env: get('credential-' + id)?.value.trim() || null})));
  // Unknown/custom configuration stays unchanged, including order and identity.
  const unused = [...before.search];
  const concepts = lines('concepts').map(label => {
    const position = unused.findIndex(c => c.label === label);
    return position >= 0 ? unused.splice(position, 1)[0] :
      {concept_id: 'concept-' + crypto.randomUUID(), label, language: 'en', aliases: []};
  });
  // Keep newly generated concept identities stable through summary/save/retries.
  if (!settingsData) entryData.draftConcepts = concepts.map(c => entryData.draftConcepts?.find(old => old.label === c.label) || c);
  const stableConcepts = settingsData ? concepts.map(c => {
    if (before.search.some(old => old.concept_id === c.concept_id)) return c;
    const existing = entryData.draftConcepts?.find(old => old.label === c.label);
    return existing || c;
  }) : entryData.draftConcepts;
  entryData.draftConcepts = stableConcepts;
  return {name: get('name').value.trim(), description: get('description').value.trim(), scope: get('scope').value.trim(),
    providers, resolvers: [...before.resolvers.filter(id => selected('resolver').includes(id) || !entryData.capabilities.resolvers.some(r => r.id === id)),
      ...selected('resolver').filter(id => !before.resolvers.includes(id))],
    search: stableConcepts, reviewer: get('reviewer').value.trim(),
    authorized_reviewers: editing ? lines('authorized-reviewers') : (get('grant-authority').checked ? [get('reviewer').value.trim()] : [])};
}
function options(kind, capabilities, active) {
  const box = get(kind + '-options'); box.replaceChildren();
  for (const item of capabilities) {
    const card = make('div'); card.className = 'service-option';
    const label = make('label'); label.className = 'choice';
    const input = make('input'); input.type = 'checkbox'; input.value = item.id;
    input.dataset.kind = kind; input.checked = active.includes(item.id);
    label.append(input, make('span', item.label)); card.append(label);
    if (item.description) card.append(make('p', item.description));
    if (item.credential_env_supported) {
      const advanced = make('details'); advanced.append(make('summary', 'Optional credential configuration'));
      const envLabel = make('label', 'Credential environment-variable name (not the key)');
      const env = make('input'); env.id = 'credential-' + item.id; env.maxLength = 100;
      env.placeholder = 'CORPUSTRAIL_PROVIDER_KEY'; env.autocomplete = 'off';
      env.value = settingsData?.fields.providers.find(p => p.adapter === item.id)?.credential_env || '';
      envLabel.append(env); advanced.append(envLabel, make('p', 'Configuration is not a connectivity test. No credential value is shown or stored.'));
      card.append(advanced);
    }
    box.append(card);
  }
}
const fieldLabels = {name: 'Project name', description: 'Topic description', scope: 'Corpus definition',
  providers: 'Discovery providers', resolvers: 'Evidence resolvers', search: 'Search concepts', authorized_reviewers: 'Authorized corpus reviewers'};
function changedFields(current = fields()) {
  return editing ? Object.keys(fieldLabels).filter(key => JSON.stringify(current[key]) !== JSON.stringify(settingsData.fields[key])) : [];
}
function summarize() {
  const current = fields(); const changed = changedFields(current);
  const box = get('summary'); box.replaceChildren();
  if (!editing) {
    const list = make('dl'); list.className = 'configuration-summary';
    for (const [label, value] of [
    ['Project', current.name], ['Topic description', current.description], ['Broad-corpus definition', current.scope || 'No separate definition configured'],
    ['Discovery providers', current.providers.map(p => entryData.capabilities.providers.find(a => a.id === p.adapter)?.label || p.id).join(', ') || 'None'],
    ['Evidence resolvers', current.resolvers.map(id => entryData.capabilities.resolvers.find(r => r.id === id)?.label || id).join(', ') || 'None'],
    ['Search concepts', current.search.map(c => c.label).join(', ') || 'None'], ['Configuration author', current.reviewer],
    ['Authorized corpus reviewers', current.authorized_reviewers.join(', ') || 'None — review observations do not grant authority'],
    ['Storage location', editing ? settingsData.location : entryData.projects_root + '/' + get('folder').value]]) {
      list.append(make('dt', label), make('dd', value));
    }
    box.append(list);
  }
  const authorityChanged = editing && JSON.stringify(current.authorized_reviewers) !== JSON.stringify(settingsData.fields.authorized_reviewers);
  get('authority-confirmation').hidden = !authorityChanged;
  get('creation-confirmation').hidden = editing;
  get('session-confirmation').hidden = !editing || !changed.length || !settingsData.has_frozen_review_sessions;
  get('scope-confirmation').hidden = !editing || !changed.includes('scope');
  if (editing) {
    const changes = make('ul');
    for (const key of changed) changes.append(make('li', fieldLabels[key]));
    const actorChanged = current.reviewer !== settingsData.fields.reviewer;
    if (actorChanged) changes.append(make('li', 'Configuration author pseudonym (recorded with a configuration change)'));
    box.append(changes.children.length ? changes : make('p', 'No configuration fields changed.'));
    get('saved-status').textContent = 'Saved configuration version ' + settingsData.version +
      (changed.length || actorChanged ? ' · Unsaved changes.' : ' · No unsaved changes.');
  }
}
function showStep(next) {
  if (editing) return;
  step = next;
  for (const group of document.querySelectorAll('[data-step]')) group.hidden = Number(group.dataset.step) !== step;
  get('back').disabled = step === 0; get('next').hidden = step === 5; get('save').hidden = step !== 5;
  get('progress').textContent = 'Step ' + (step + 1) + ' of 6';
  if (step === 5) summarize();
  get('section-' + step).focus();
}
function validStep(index = step) {
  for (const field of document.querySelectorAll('[data-step="' + index + '"] input, [data-step="' + index + '"] textarea')) {
    if (!field.reportValidity()) return false;
  }
  return true;
}
function populateSettings() {
  entryData.draftConcepts = [];
  for (const id of ['name', 'description', 'scope', 'reviewer']) get(id).value = settingsData.fields[id];
  get('concepts').value = settingsData.fields.search.map(c => c.label).join('\n');
  get('authorized-reviewers').value = settingsData.fields.authorized_reviewers.join('\n');
  get('scope').required = settingsData.definition.scope_present;
  options('provider', entryData.capabilities.providers, settingsData.fields.providers.map(p => p.adapter));
  options('resolver', entryData.capabilities.resolvers, settingsData.fields.resolvers);
  get('definition-version').textContent = settingsData.definition.scope_present ? 'The saved definition belongs to configuration version ' + settingsData.version + '.' : 'No separate corpus definition is configured. Other settings can be saved without inventing one.';
  get('configuration-location').textContent = 'Project location: ' + settingsData.location;
  get('configuration-definition').textContent = 'Definition/configuration hash: ' + settingsData.definition.sha256;
  const history = get('configuration-history'); history.replaceChildren();
  for (const item of settingsData.history) history.append(make('li', 'Version ' + item.version + ' · ' + item.created_by + ' · ' + item.created_at));
  requestId = null;
  for (const id of ['confirm-authority', 'confirm-sessions', 'confirm-scope']) get(id).checked = false;
  summarize();
}
async function initialize() {
  entryData = await request('projects');
  get(editing ? 'nav-settings' : 'nav-projects').setAttribute('aria-current', 'page');
  if (location.pathname !== '/projects/new' && !editing) {
    get('entry').hidden = false; get('root-location').textContent = 'Projects location: ' + entryData.projects_root;
    renderProjects(entryData); return;
  }
  if (editing) {
    settingsData = await request('project-settings');
    get('reload-settings').hidden = false; get('discard').hidden = false; get('configuration-info').hidden = false;
    get('setup-title').textContent = 'Project Settings'; get('save').textContent = 'Save Changes';
    get('new-location').hidden = true; get('folder').required = false;
    get('initial-authority').hidden = true; get('existing-authority').hidden = false;
    get('project-form').className = 'settings-form';
    get('project-form').prepend(get('save-actions'));
    get('progress').textContent = 'Edit the sections you need, then Save Changes. Nothing is saved while you type.';
    get('section-5').textContent = 'Changes before saving';
    get('return-link').textContent = 'Return to dashboard'; get('return-link').href = '/dashboard';
    for (const group of document.querySelectorAll('[data-step]')) group.hidden = false;
    get('back').hidden = true; get('next').hidden = true; get('save').hidden = false;
    populateSettings();
  } else get('scope').required = true;
  get('setup').hidden = false;
  if (!editing) {
    options('provider', entryData.capabilities.providers, []);
    options('resolver', entryData.capabilities.resolvers, []);
    showStep(0);
  }
}
function renderProjects(page) {
  for (const item of page.items) {
    const active = !item.unavailable && item.handle === page.active_handle;
    const card = make('article'); card.className = 'project-card' + (active ? ' active-project' : '');
    const heading = make('div'); heading.className = 'project-card-heading'; heading.append(make('h2', item.name));
    if (active) { const badge = make('span', 'Active project'); badge.className = 'badge'; heading.append(badge); }
    card.append(heading);
    if (item.unavailable) card.append(make('p', 'Unavailable or incompatible project; no upgrade was attempted.'));
    else {
      const path = make('p', item.location); path.className = 'project-location'; card.append(path);
      const actions = make('div'); actions.className = 'project-actions'; actions.setAttribute('role', 'group');
      actions.setAttribute('aria-label', 'Project actions');
      const button = make('button', 'Open Project'); button.type = 'button';
      button.onclick = async () => {
        button.disabled = true;
        try { const result = await request('projects/open', {handle: item.handle}); location.assign(result.dashboard_url); }
        catch (error) { message(error.message); button.disabled = false; }
      };
      actions.append(button);
      if (active) {
        const close = make('button', 'Close Project'); close.type = 'button';
        close.onclick = async () => {
          if (busy) return;
          busy = true; close.disabled = true;
          try { await request('projects/close', {}); location.assign('/projects'); }
          catch (error) { message(error.message); busy = false; close.disabled = false; }
        };
        actions.append(close);
      }
      const remove = make('button', 'Move to Trash…'); remove.type = 'button'; remove.className = 'danger-secondary';
      remove.disabled = !item.removal?.available;
      remove.onclick = () => prepareTrash(item.handle);
      actions.append(remove); card.append(actions);
      const reason = active ? 'Close this project before removal. Other processes may still keep it in use.' :
        (!item.removal?.available ? item.removal?.reason || 'Move to Trash is unavailable.' : '');
      if (reason) { const helper = make('p', reason); helper.className = 'muted'; card.append(helper); }
    }
    get('project-list').append(card);
  }
  get('more-projects').hidden = page.next_offset === null;
  get('more-projects').onclick = async () => {
    try { renderProjects(await request('projects?offset=' + page.next_offset)); } catch (error) { message(error.message); }
  };
}
const trashSchema = 'corpustrail-project-trash/v1';
let trashPlan = null;
async function refreshProjects() {
  entryData = await request('projects'); get('project-list').replaceChildren(); renderProjects(entryData);
}
async function prepareTrash(handle) {
  if (busy) return;
  busy = true;
  try {
    trashPlan = await request('projects/trash/prepare', {handle}, trashSchema);
    get('trash-name').textContent = trashPlan.name; get('trash-location').textContent = trashPlan.location;
    get('trash-folder-name').textContent = trashPlan.folder; get('trash-folder').value = '';
    get('trash-execute').disabled = true; get('entry').hidden = true; get('trash-confirmation').hidden = false;
    get('trash-folder').focus(); message('Review the selected project before confirming.');
  } catch (error) { message(error.message); }
  finally { busy = false; }
}
get('trash-folder').addEventListener('input', () => {
  get('trash-execute').disabled = busy || !trashPlan || get('trash-folder').value !== trashPlan.folder;
});
get('trash-cancel').onclick = async () => {
  if (busy) return;
  busy = true;
  try {
    if (trashPlan) await request('projects/trash/cancel', {confirmation: trashPlan.confirmation}, trashSchema);
    trashPlan = null; get('trash-confirmation').hidden = true; get('entry').hidden = false;
    await refreshProjects(); message('Confirmation closed. Cancelling does not move or restore any project.');
    get('open-existing').setAttribute('tabindex', '-1'); get('open-existing').focus();
  } catch (error) { message(error.message); }
  finally { busy = false; }
};
get('trash-execute').onclick = async () => {
  if (busy || !trashPlan || get('trash-folder').value !== trashPlan.folder) return;
  busy = true; get('trash-execute').disabled = true; get('trash-cancel').disabled = true;
  const plan = trashPlan; trashPlan = null; // Never automatically replay a removal.
  try {
    const result = await request('projects/trash/execute', {confirmation: plan.confirmation, folder: get('trash-folder').value}, trashSchema);
    get('trash-confirmation').hidden = true; get('entry').hidden = false;
    await refreshProjects(); message(result.message);
  } catch (error) { message(error.message + ' Refresh Projects and inspect the project before continuing.'); }
  finally { busy = false; get('trash-cancel').disabled = false; }
};
get('name').addEventListener('input', () => {
  if (!editing && !get('folder').dataset.edited) get('folder').value = get('name').value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'project';
  get('intended-location').textContent = 'Will be saved at: ' + entryData.projects_root + '/' + get('folder').value;
});
get('folder').addEventListener('input', () => { get('folder').dataset.edited = 'true'; get('intended-location').textContent = 'Will be saved at: ' + entryData.projects_root + '/' + get('folder').value; });
get('project-form').addEventListener('input', () => {
  requestId = null;
  for (const id of ['confirm-authority', 'confirm-sessions', 'confirm-scope']) get(id).checked = false;
  if (editing) summarize();
});
// Confirmation toggles must not clear their own checks.
for (const id of ['confirm-authority', 'confirm-sessions', 'confirm-scope']) get(id).addEventListener('input', event => event.stopPropagation());
get('discard').onclick = () => { if (!busy) { populateSettings(); message('Unsaved changes discarded. Saved settings and research data are unchanged.'); } };
get('back').onclick = () => { if (!busy) showStep(Math.max(0, step - 1)); };
get('next').onclick = () => { if (!busy && validStep()) showStep(Math.min(5, step + 1)); };
get('project-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  if (!editing && step !== 5) { if (validStep()) showStep(Math.min(5, step + 1)); return; }
  if (editing) {
    for (let index = 0; index < 5; index++) if (!validStep(index)) return;
    summarize();
    if (!changedFields().length) return message(fields().reviewer !== settingsData.fields.reviewer ?
      'A pseudonym-only edit does not change configuration. No new revision was created; the pseudonym is recorded when configuration changes.' :
      'No configuration fields changed; no new revision was created.');
  }
  if (!get('scope-confirmation').hidden && !get('confirm-scope').checked) return message('Confirm the broad-corpus definition change before saving.');
  if (!get('authority-confirmation').hidden && !get('confirm-authority').checked) return message('Confirm the displayed authority configuration before saving.');
  if (!get('session-confirmation').hidden && !get('confirm-sessions').checked) return message('Confirm the review-session safeguard before saving changes.');
  busy = true; get('save').disabled = true; requestId ||= crypto.randomUUID();
  for (const group of document.querySelectorAll('[data-step]')) group.disabled = true;
  try {
    // Creation confirms the explicit radio choice and displayed summary. Settings
    // changes retain their separate authority confirmation. Neither grants defaults.
    const body = {request_id: requestId, fields: fields(), confirm_authority: editing ? get('confirm-authority').checked : get('grant-authority').checked};
    let result;
    if (editing) result = await request('project-settings/save', {...body, project_handle: settingsData.project_handle,
      revision: settingsData.revision, confirm_session_change: get('confirm-sessions').checked});
    else result = await request('projects/create', {...body, folder: get('folder').value});
    if (editing) {
      settingsData = await request('project-settings?handle=' + settingsData.project_handle);
      message(result.changed ? 'Changes saved as configuration version ' + result.version + '. No review or corpus decision was changed.' : 'No configuration fields changed; no new revision was created.');
      populateSettings();
    } else location.assign(result.dashboard_url + '#created');
  } catch (error) { message(error.message); }
  finally {
    busy = false; get('save').disabled = false;
    for (const group of document.querySelectorAll('[data-step]')) group.disabled = false;
  }
});
initialize().catch(error => message(error.message));
