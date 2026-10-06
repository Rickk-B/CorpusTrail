'use strict';
// Operational read DTOs only. Never reuse this client/API for method-blind review.
const byId = id => document.getElementById(id);
const token = document.querySelector('meta[name="corpustrail-session"]').content;
const labels = {included: 'In corpus', excluded: 'Out of corpus', insufficient_evidence: 'Insufficient evidence',
  unresolved: 'Awaiting corpus decision', not_reviewed: 'Awaiting corpus decision'};
const serviceNames = {openalex: 'OpenAlex', europepmc: 'Europe PMC', crossref: 'Crossref',
  semantic_scholar: 'Semantic Scholar', semanticscholar: 'Semantic Scholar'};
const serviceName = value => Object.hasOwn(serviceNames, value) ? serviceNames[value] : value;
const text = (id, value) => { byId(id).textContent = value; };
function node(tag, value) { const item = document.createElement(tag); item.textContent = value; return item; }
function failure(error) { text('message', error.message); }
async function api(path) {
  const response = await fetch('/api/v1/' + path, {headers: {'X-CorpusTrail-Session': token}, cache: 'no-store'});
  const value = await response.json();
  if (!response.ok) throw new Error(value.error.message);
  text('message', ''); return value;
}
function bib(paper) {
  const b = paper.bibliography;
  return [b.authors.length ? b.authors.join(', ') : 'Authors not available',
    b.year || 'Year not available', b.source].filter(Boolean).join(' · ');
}
function identifierLine(items) {
  return items.filter(item => ['doi', 'pmid', 'pmcid'].includes(item.scheme))
    .map(item => item.scheme.toUpperCase() + ': ' + item.value).join(' · ');
}
function identifierUrl(item) {
  // Fixed official origins only; identifiers are data, never arbitrary URLs.
  if (item.scheme === 'doi' && /^10\.\d{4,9}\/\S+$/.test(item.value)) {
    return 'https://doi.org/' + item.value.split('/').map(encodeURIComponent).join('/');
  }
  if (item.scheme === 'pmid' && /^[0-9]+$/.test(item.value)) return 'https://pubmed.ncbi.nlm.nih.gov/' + item.value + '/';
  if (item.scheme === 'pmcid' && /^PMC[0-9]+$/.test(item.value)) return 'https://pmc.ncbi.nlm.nih.gov/articles/' + item.value + '/';
  return null;
}
function identifierNodes(items) {
  const box = node('span', '');
  for (const item of items.filter(item => ['doi', 'pmid', 'pmcid'].includes(item.scheme))) {
    if (box.children.length) box.append(node('span', ' · '));
    box.append(node('span', item.scheme.toUpperCase() + ': '));
    const url = identifierUrl(item);
    const value = node(url ? 'a' : 'span', item.value);
    if (url) {
      value.href = url; value.target = '_blank'; value.rel = 'noopener noreferrer';
      value.setAttribute('aria-label', item.scheme.toUpperCase() + ': ' + item.value + ' (opens in a new tab)');
    }
    box.append(value);
  }
  return box;
}
function discoveryLine(sources) {
  return sources.length ? 'Discovered via ' + sources.map(serviceName).join(', ') : '';
}
function reviewLabel(review) {
  // Draft counts cannot establish that a review was recorded or completed.
  return review.human_observations ? 'Human review recorded' : 'No human review recorded';
}
function evidenceLabels(e) {
  const items = ['Metadata', e.abstract_available ? 'Abstract available' : 'No abstract',
    e.verified_structured_text ? 'Verified full/structured text' : 'No verified full text'];
  if (e.pending_identity) items.push('Pending documents: ' + e.pending_identity);
  if (e.mismatch_or_invalid) items.push('Invalid or mismatched documents: ' + e.mismatch_or_invalid);
  return items;
}
function chips(values, label) {
  const box = node('div', ''); box.className = 'chips'; box.setAttribute('role', 'group'); box.setAttribute('aria-label', label);
  for (const value of values) { const chip = node('span', value); chip.className = 'badge'; box.append(chip); }
  return box;
}
function statusNodes(paper) {
  const box = node('div', ''); box.className = 'paper-status';
  box.append(chips([labels[paper.membership.state]], 'Corpus decision'),
    chips([reviewLabel(paper.review)], 'Human review'), chips(evidenceLabels(paper.evidence), 'Evidence status'));
  return box;
}
async function dashboard() {
  const data = await api('dashboard');
  byId('dashboard').hidden = false;
  text('project-name', data.project.name); text('description', data.project.description);
  const separate = data.project.definition_origin === 'review_scope';
  const distinct = separate && data.project.broad_corpus_definition !== data.project.description;
  byId('definition-group').hidden = !distinct;
  text('definition', distinct ? data.project.broad_corpus_definition : '');
  text('definition-note', separate ? (distinct ? '' : 'Corpus definition matches the project description.') : 'No separate corpus definition configured.');
  const box = byId('summaries'); box.replaceChildren();
  const m = data.membership;
  for (const [heading, rows] of [
    ['Corpus', ['Papers: ' + data.papers, 'In corpus: ' + m.included, 'Out of corpus: ' + m.excluded,
      'Insufficient evidence: ' + m.insufficient_evidence, 'Awaiting corpus decision: ' + (m.not_reviewed + m.unresolved)]],
    ['Review activity', ['Papers with recorded human review: ' + data.review.human_reviewed_papers,
      'Papers with published corpus decisions: ' + data.review.published_corpus_decisions,
      'Review sessions: ' + data.review.sessions]],
    ['Evidence', ['Abstract available: ' + data.evidence.abstract_available_papers,
      'Verified full/structured text available: ' + data.evidence.verified_structured_text_papers,
      'Papers with pending documents: ' + data.evidence.pending_document_papers,
      'Papers with invalid or mismatched documents: ' + data.evidence.mismatch_or_invalid_papers]]
  ]) { const card = node('div', ''); card.className = 'card'; card.append(node('h2', heading)); rows.forEach(row => card.append(node('p', row))); box.append(card); }
  const details = byId('dashboard-details'); details.replaceChildren(node('summary', 'Activity and identity details'),
    node('p', 'Papers with draft history: ' + data.review.papers_with_draft_history),
    node('p', 'Session updates: ' + data.review.session_updates), node('p', data.review.notice),
    node('p', 'Observations with recorded identity warnings: ' + data.identity_issues.recorded_observations_with_issues),
    node('p', data.identity_issues.notice));
  text('providers', 'Discovery providers: ' + (data.providers.map(serviceName).join(', ') || 'None configured'));
  text('resolvers', 'Evidence resolvers: ' + (data.resolvers.map(serviceName).join(', ') || 'None configured'));
}
let pageState;
let listGeneration = 0;
async function catalogue(cursor = null) {
  const generation = ++listGeneration;
  const params = new URLSearchParams({q: byId('search').value, membership: byId('membership').value,
    evidence: byId('evidence-filter').value, review: byId('review-filter').value,
    sort: byId('sort').value, limit: byId('page-size').value});
  if (cursor) params.set('cursor', cursor);
  const page = await api('papers?' + params);
  if (generation !== listGeneration) return;
  pageState = page; byId('catalogue').hidden = false;
  text('page-count', page.total ? 'Showing ' + (page.offset + 1) + '–' + (page.offset + page.items.length) + ' of ' + page.total + ' papers' : 'No matching papers');
  const box = byId('paper-list'); box.replaceChildren();
  for (const paper of page.items) {
    const card = node('article', ''); const heading = node('h2', '');
    const link = node('a', paper.bibliography.title || 'Title not available'); link.href = '/papers/' + paper.handle;
    heading.append(link); card.append(heading, node('p', bib(paper)), statusNodes(paper));
    const ids = identifierLine(paper.identifiers);
    if (ids) { const line = node('p', ''); line.className = 'muted identifiers'; line.append(identifierNodes(paper.identifiers)); card.append(line); }
    const sources = discoveryLine(paper.sources);
    if (sources) { const line = node('p', sources); line.className = 'muted'; card.append(line); }
    box.append(card);
  }
  byId('previous-page').disabled = !page.previous_cursor; byId('next-page').disabled = !page.next_cursor;
}
let paperHandle;
let provenanceState;
let provenanceGeneration = 0;
function copyIdentifier(label, value) {
  const row = node('div', ''); row.className = 'technical-identifier';
  const input = node('input', ''); input.type = 'text'; input.readOnly = true; input.value = value;
  input.setAttribute('aria-label', label); const button = node('button', 'Copy'); button.type = 'button';
  button.setAttribute('aria-label', 'Copy ' + label);
  button.onclick = async () => {
    try { await navigator.clipboard.writeText(value); text('copy-status', label + ' copied.'); }
    catch (_) { input.focus(); input.select(); text('copy-status', 'Copy unavailable. Identifier selected for manual copying.'); }
  };
  row.append(node('span', label), input, button); return row;
}
function lineageRows(data) {
  const list = node('ul', '');
  if (data.canonical_selection) {
    for (const [field, source] of Object.entries(data.canonical_selection.fields)) {
      list.append(node('li', field + ' selected from: ' + (source || 'No value available')));
    }
  }
  // This summary does not replace records: the complete current page is below.
  for (const item of data.items) {
    const record = item.record || {}; const source = record.source || {};
    const description = [item.observation_id || item.event_id || item.identifier_id || 'Provenance record',
      source.producer_id || record.producer_id || item.provider,
      record.created_at || source.observed_at || item.created_at,
      item.status].filter(Boolean).join(' · ');
    list.append(node('li', description));
  }
  return list;
}
async function provenance(cursor = null) {
  const generation = ++provenanceGeneration;
  const params = new URLSearchParams({section: byId('provenance-section').value, limit: '25'});
  if (cursor) params.set('cursor', cursor);
  const data = await api('papers/' + paperHandle + '/provenance?' + params);
  if (generation !== provenanceGeneration) return;
  provenanceState = data;
  byId('technical-identifiers').replaceChildren(copyIdentifier('CorpusTrail paper ID', data.paper_id),
    ...data.summary.identifiers.map(item => copyIdentifier(item.scheme === 'openalex' ? 'OpenAlex ID' : item.scheme.toUpperCase(), item.value)));
  text('provenance-sources', discoveryLine(data.summary.sources) || 'Discovery source not recorded.');
  text('selection-summary', 'Canonical metadata selection available. Rule: ' + data.summary.canonical_selection_rule);
  text('provenance-count', 'Records in this category: ' + data.total + '. Showing ' + data.items.length + ' on this page.');
  byId('lineage-records').replaceChildren(lineageRows(data));
  text('provenance-text', JSON.stringify({canonical_selection: data.canonical_selection, records: data.items}, null, 2));
  byId('provenance-previous').disabled = !data.previous_cursor; byId('provenance-next').disabled = !data.next_cursor;
}
let documentState;
async function readDocument(handle, offset = 0) {
  const data = await api('papers/' + paperHandle + '/evidence/' + handle + '?offset=' + offset);
  documentState = data; text('document-text', data.text); byId('document-text').hidden = false;
  text('document-position', 'Characters ' + (data.offset + 1) + '–' + (data.offset + data.text.length) + ' of ' + data.total_characters + '.');
  byId('document-next').hidden = data.next_offset === null;
}
async function detail(handle) {
  paperHandle = handle;
  const data = await api('papers/' + handle); const paper = data.paper;
  byId('detail').hidden = false; text('paper-title', paper.bibliography.title || 'Title not available');
  text('bibliography', bib(paper)); byId('identifiers').replaceChildren(identifierNodes(paper.identifiers));
  text('paper-sources', discoveryLine(paper.sources));
  byId('paper-status').replaceChildren(statusNodes(paper));
  text('abstract', paper.abstract || 'No abstract is currently available in CorpusTrail.');
  const reps = byId('representations'); reps.replaceChildren();
  const controls = byId('document-controls'); controls.replaceChildren();
  for (const rep of paper.representations) {
    if (rep.readable) { const button = node('button', 'Read verified structured text'); button.onclick = () => readDocument(rep.handle).catch(failure); controls.append(button); }
    else if (rep.validity === 'pending_identity') reps.append(node('p', 'Pending document — identity not verified; not offered as trusted evidence.'));
    else if (['mismatch', 'invalid'].includes(rep.validity)) reps.append(node('p', 'Invalid or mismatched document — not offered as trusted evidence.'));
  }
  if (!paper.representations.some(rep => rep.readable)) reps.prepend(node('p', 'No full-text document is currently available to read as verified evidence in CorpusTrail.'));
}
byId('filters').addEventListener('submit', event => { event.preventDefault(); catalogue().catch(failure); });
byId('previous-page').onclick = () => catalogue(pageState.previous_cursor).catch(failure);
byId('next-page').onclick = () => catalogue(pageState.next_cursor).catch(failure);
byId('advanced').addEventListener('toggle', () => { if (byId('advanced').open && !provenanceState) provenance().catch(failure); });
byId('provenance-section').onchange = () => provenance().catch(failure);
byId('provenance-previous').onclick = () => provenance(provenanceState.previous_cursor).catch(failure);
byId('provenance-next').onclick = () => provenance(provenanceState.next_cursor).catch(failure);
byId('document-next').onclick = () => readDocument(documentState.representation_handle, documentState.next_offset).catch(failure);
const match = location.pathname.match(/^\/papers\/([0-9a-f]{64})$/);
byId(match || location.pathname === '/papers' ? 'nav-papers' : 'nav-dashboard').setAttribute('aria-current', 'page');
if (match) detail(match[1]).catch(failure);
else if (location.pathname === '/papers') catalogue().catch(failure);
else dashboard().catch(failure);
