'use strict';
// Guided forms only. Scientific validation and writes belong to application services.
const get = id => document.getElementById(id);
const sessionToken = document.querySelector('meta[name="corpustrail-session"]').content;
const formSchema = 'corpustrail-project-form/v1';
const make = (tag, value = '') => { const el = document.createElement(tag); el.textContent = value; return el; };
let entryData, settingsData, step = 0, requestId = null, busy = false;
const editing = location.pathname === '/settings';
function message(value) { get('message').textContent = value; }
async function request(path, body) {
  const options = {headers: {'X-CorpusTrail-Session': sessionToken}, cache: 'no-store'};
  if (body !== undefined) {
    options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
    options.headers['X-CorpusTrail-CSRF'] = sessionToken;
    options.body = JSON.stringify({schema: formSchema, ...body});
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
  const providerOrder = [...before.providers.filter(p => chosenProviders.includes(p.id)).map(p => p.id),
    ...chosenProviders.filter(id => !before.providers.some(p => p.id === id))];
  const providers = providerOrder.map(id => ({id, adapter: id, credential_env: get('credential-' + id)?.value.trim() || null}));
  // Unknown/custom configuration stays unchanged, not falsely offered as built-in functionality.
  providers.push(...before.providers.filter(p => !entryData.capabilities.providers.some(a => a.id === p.adapter)));
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
    providers, resolvers: [...selected('resolver'), ...before.resolvers.filter(id => !entryData.capabilities.resolvers.some(r => r.id === id))],
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
      env.value = settingsData?.fields.providers.find(p => p.id === item.id)?.credential_env || '';
      envLabel.append(env); advanced.append(envLabel, make('p', 'Configuration is not a connectivity test. No credential value is shown or stored.'));
      card.append(advanced);
    }
    box.append(card);
  }
}
function summarize() {
  const current = fields(); const box = get('summary'); box.replaceChildren();
  for (const [label, value] of [
    ['Project', current.name], ['Topic description', current.description], ['Broad-corpus definition', current.scope || 'No separate definition configured'],
    ['Discovery providers', current.providers.map(p => entryData.capabilities.providers.find(a => a.id === p.adapter)?.label || p.id).join(', ') || 'None'],
    ['Evidence resolvers', current.resolvers.map(id => entryData.capabilities.resolvers.find(r => r.id === id)?.label || id).join(', ') || 'None'],
    ['Search concepts', current.search.map(c => c.label).join(', ') || 'None'], ['Configuration author / reviewer pseudonym', current.reviewer],
    ['Authorized corpus reviewers', current.authorized_reviewers.join(', ') || 'None — review observations do not grant authority'],
    ['Storage location', editing ? settingsData.location : entryData.projects_root + '/' + get('folder').value]]) {
    box.append(make('h2', label), make('p', value));
  }
  const authorityChanged = editing ? JSON.stringify(current.authorized_reviewers) !== JSON.stringify(settingsData.fields.authorized_reviewers) : current.authorized_reviewers.length > 0;
  get('authority-confirmation').hidden = !authorityChanged;
  get('session-confirmation').hidden = !editing || !settingsData.has_frozen_review_sessions;
  if (editing) {
    box.append(make('h2', 'Changes to saved configuration'));
    const changes = make('ul');
    for (const [key, label] of Object.entries({name: 'Project name', description: 'Topic description', scope: 'Corpus definition',
      providers: 'Discovery providers', resolvers: 'Evidence resolvers', search: 'Search concepts', authorized_reviewers: 'Authorized corpus reviewers'})) {
      if (JSON.stringify(current[key]) !== JSON.stringify(settingsData.fields[key])) changes.append(make('li', label));
    }
    box.append(changes.children.length ? changes : make('p', 'No configuration fields changed.'));
    box.append(make('p', 'Saving appends a configuration revision. Existing models, concept extensions and advanced policy settings are preserved. No reviews or membership are rewritten.'));
  }
}
function showStep(next) {
  step = next;
  for (const group of document.querySelectorAll('[data-step]')) group.hidden = Number(group.dataset.step) !== step;
  get('back').disabled = step === 0; get('next').hidden = step === 5; get('save').hidden = step !== 5;
  get('progress').textContent = 'Step ' + (step + 1) + ' of 6';
  if (step === 5) summarize();
  document.querySelector('[data-step="' + step + '"] legend').focus();
}
function validStep() {
  for (const field of document.querySelectorAll('[data-step="' + step + '"] input, [data-step="' + step + '"] textarea')) {
    if (!field.reportValidity()) return false;
  }
  return true;
}
async function initialize() {
  entryData = await request('projects');
  if (location.pathname !== '/projects/new' && !editing) {
    get('entry').hidden = false; get('root-location').textContent = 'Projects location: ' + entryData.projects_root;
    renderProjects(entryData); return;
  }
  if (editing) {
    settingsData = await request('project-settings');
    get('reload-settings').hidden = false;
    get('setup-title').textContent = 'Project Settings'; get('save').textContent = 'Save Changes';
    get('new-location').hidden = true; get('folder').required = false;
    get('initial-authority').hidden = true; get('existing-authority').hidden = false;
    for (const id of ['name', 'description', 'scope', 'reviewer']) get(id).value = settingsData.fields[id];
    get('concepts').value = settingsData.fields.search.map(c => c.label).join('\n');
    get('authorized-reviewers').value = settingsData.fields.authorized_reviewers.join('\n');
    get('saved-status').textContent = 'Saved configuration version ' + settingsData.version + ' · ' + settingsData.location + '. Changes remain unsaved until Save Changes.';
    get('definition-version').textContent = settingsData.definition.scope_present ? 'The saved definition belongs to configuration version ' + settingsData.version + '.' : 'No separate corpus definition is configured. Other settings can be saved without inventing one.';
  } else get('scope').required = true;
  options('provider', entryData.capabilities.providers, settingsData?.fields.providers.map(p => p.id) || []);
  options('resolver', entryData.capabilities.resolvers, settingsData?.fields.resolvers || []);
  for (const legend of document.querySelectorAll('legend')) legend.tabIndex = -1;
  get('setup').hidden = false; showStep(0);
}
function renderProjects(page) {
  for (const item of page.items) {
    const card = make('article'); card.append(make('h2', item.name));
    if (item.unavailable) card.append(make('p', 'Unavailable or incompatible project; no upgrade was attempted.'));
    else {
      card.append(make('p', item.location)); const button = make('button', 'Open project'); button.type = 'button';
      button.onclick = async () => {
        button.disabled = true;
        try { const result = await request('projects/open', {handle: item.handle}); location.assign(result.dashboard_url); }
        catch (error) { message(error.message); button.disabled = false; }
      };
      card.append(button);
    }
    get('project-list').append(card);
  }
  get('more-projects').hidden = page.next_offset === null;
  get('more-projects').onclick = async () => {
    try { renderProjects(await request('projects?offset=' + page.next_offset)); } catch (error) { message(error.message); }
  };
}
get('name').addEventListener('input', () => {
  if (!editing && !get('folder').dataset.edited) get('folder').value = get('name').value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'project';
  get('intended-location').textContent = 'Will be saved at: ' + entryData.projects_root + '/' + get('folder').value;
});
get('folder').addEventListener('input', () => { get('folder').dataset.edited = 'true'; get('intended-location').textContent = 'Will be saved at: ' + entryData.projects_root + '/' + get('folder').value; });
get('project-form').addEventListener('input', () => {
  requestId = null; get('confirm-authority').checked = false; get('confirm-sessions').checked = false;
  if (editing) get('saved-status').textContent = 'Saved configuration version ' + settingsData.version + ' · Unsaved changes. Review the summary before Save Changes.';
});
// Confirmation toggles must not clear their own checks.
for (const id of ['confirm-authority', 'confirm-sessions']) get(id).addEventListener('input', event => event.stopPropagation());
get('back').onclick = () => { if (!busy) showStep(Math.max(0, step - 1)); };
get('next').onclick = () => { if (!busy && validStep()) showStep(Math.min(5, step + 1)); };
get('project-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (step !== 5) { if (validStep()) showStep(Math.min(5, step + 1)); return; }
  if (busy) return;
  if (!get('authority-confirmation').hidden && !get('confirm-authority').checked) return message('Confirm the displayed authority configuration before saving.');
  if (!get('session-confirmation').hidden && !get('confirm-sessions').checked) return message('Confirm the review-session safeguard before saving changes.');
  busy = true; get('save').disabled = true; requestId ||= crypto.randomUUID();
  for (const group of document.querySelectorAll('[data-step]')) group.disabled = true;
  try {
    const body = {request_id: requestId, fields: fields(), confirm_authority: get('confirm-authority').checked};
    let result;
    if (editing) result = await request('project-settings/save', {...body, project_handle: settingsData.project_handle,
      revision: settingsData.revision, confirm_session_change: get('confirm-sessions').checked});
    else result = await request('projects/create', {...body, folder: get('folder').value});
    if (editing) {
      settingsData = await request('project-settings?handle=' + settingsData.project_handle);
      message(result.changed ? 'Changes saved as configuration version ' + result.version + '. No review or corpus decision was changed.' : 'No configuration fields changed; no new revision was created.');
      get('saved-status').textContent = 'Saved configuration version ' + settingsData.version + '. No unsaved changes.';
      get('definition-version').textContent = 'Saved definition/configuration version ' + settingsData.version + '.';
      requestId = null; get('confirm-authority').checked = false; get('confirm-sessions').checked = false;
      showStep(0);
    } else location.assign(result.dashboard_url + '#created');
  } catch (error) { message(error.message); }
  finally {
    busy = false; get('save').disabled = false;
    for (const group of document.querySelectorAll('[data-step]')) group.disabled = false;
  }
});
initialize().catch(error => message(error.message));
