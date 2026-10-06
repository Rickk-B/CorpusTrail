'use strict';
// Operational read DTOs only. Do not reuse this client or API for blinded review.
const byId = id => document.getElementById(id);
const token = document.querySelector('meta[name="corpustrail-session"]').content;
const labels = {included: 'Included', excluded: 'Excluded', insufficient_evidence: 'Insufficient evidence',
  unresolved: 'Unresolved', not_reviewed: 'Not reviewed for membership'};
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
  return [b.authors.length ? b.authors.join(', ') : 'Authors unavailable', b.year || 'Year unavailable', b.source || 'Source unavailable'].join(' · ');
}
function evidenceLine(e) {
  return 'Metadata ✓ · Abstract ' + (e.abstract_available ? '✓' : 'unavailable') +
    ' · Verified structured/full-text body ' + (e.verified_structured_text ? '✓' : 'unavailable') +
    (e.pending_identity ? ' · Pending identity: ' + e.pending_identity : '') +
    (e.mismatch_or_invalid ? ' · Mismatch/invalid: ' + e.mismatch_or_invalid : '');
}
function reviewLine(review) {
  return (review.human_observations ? 'Human review observations: ' + review.human_observations : 'No human review observation recorded') +
    (review.sessions_with_draft_history ? ' · Draft history in ' + review.sessions_with_draft_history + ' session(s)' : '') +
    (review.other_observations ? ' · Other non-human observations: ' + review.other_observations : '');
}
function identifierLine(items) { return items.map(item => item.scheme.toUpperCase() + ': ' + item.value).join(' · ') || 'No exact identifiers available'; }
function statusNodes(paper) {
  const box = node('div', '');
  box.append(node('p', 'Corpus membership: ' + labels[paper.membership.state] +
    (paper.membership.authority_state === 'human_authorized' ? ' — human-authorized' : ' — no authoritative judgment')),
    node('p', reviewLine(paper.review)), node('p', evidenceLine(paper.evidence)));
  return box;
}
async function dashboard() {
  const data = await api('dashboard');
  byId('dashboard').hidden = false;
  text('project-name', data.project.name); text('description', data.project.description);
  text('definition', data.project.broad_corpus_definition);
  text('definition-note', data.project.definition_origin === 'review_scope' ? 'Configured review scope; historical review packets retain their original question.' : 'Project description shown because no separate review scope is configured.');
  const box = byId('summaries'); box.replaceChildren();
  for (const [heading, rows] of [
    ['Corpus', ['Canonical papers: ' + data.papers, ...Object.entries(data.membership).map(([key, count]) => labels[key] + ': ' + count)]],
    ['Human review / sessions', ['Human-reviewed papers: ' + data.review.human_reviewed_papers,
      'Papers with draft history: ' + data.review.papers_with_draft_history, 'Review sessions: ' + data.review.sessions,
      'Session updates: ' + data.review.session_updates, data.review.notice]],
    ['Evidence', ['Abstract available: ' + data.evidence.abstract_available_papers,
      'Verified structured body: ' + data.evidence.verified_structured_text_papers,
      'Papers with pending documents: ' + data.evidence.pending_document_papers,
      'Papers with mismatch/invalid documents: ' + data.evidence.mismatch_or_invalid_papers]],
    ['Identity', ['Observations with recorded issues: ' + data.identity_issues.recorded_observations_with_issues, data.identity_issues.notice]]
  ]) { const card = node('div', ''); card.className = 'card'; card.append(node('h2', heading)); rows.forEach(row => card.append(node('p', row))); box.append(card); }
  text('providers', 'Discovery providers: ' + (data.providers.join(', ') || 'None configured'));
  text('resolvers', 'Evidence resolvers: ' + (data.resolvers.join(', ') || 'None configured'));
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
    const link = node('a', paper.bibliography.title || 'Title unavailable'); link.href = '/papers/' + paper.handle;
    heading.append(link); card.append(heading, node('p', bib(paper)), node('p', identifierLine(paper.identifiers)),
      statusNodes(paper), node('p', 'Sources: ' + (paper.sources.join(', ') || 'Not recorded'))); box.append(card);
  }
  byId('previous-page').disabled = !page.previous_cursor; byId('next-page').disabled = !page.next_cursor;
}
let paperHandle;
let provenanceState;
let provenanceGeneration = 0;
async function provenance(cursor = null) {
  const generation = ++provenanceGeneration;
  const params = new URLSearchParams({section: byId('provenance-section').value, limit: '25'});
  if (cursor) params.set('cursor', cursor);
  const data = await api('papers/' + paperHandle + '/provenance?' + params);
  if (generation !== provenanceGeneration) return;
  provenanceState = data;
  text('technical-id', 'Canonical paper ID: ' + data.paper_id);
  text('provenance-count', 'Provenance records: ' + data.total + '; this page: ' + data.items.length);
  text('provenance-text', JSON.stringify({canonical_selection: data.canonical_selection, records: data.items}, null, 2));
  byId('provenance-previous').disabled = !data.previous_cursor; byId('provenance-next').disabled = !data.next_cursor;
}
let documentState;
async function readDocument(handle, offset = 0) {
  const data = await api('papers/' + paperHandle + '/evidence/' + handle + '?offset=' + offset);
  documentState = data; text('document-text', data.text); byId('document-text').hidden = false;
  text('document-position', 'Characters ' + (data.offset + 1) + '–' + (data.offset + data.text.length) + ' of ' + data.total_characters + '. ' + data.notice);
  byId('document-next').hidden = data.next_offset === null;
}
async function detail(handle) {
  paperHandle = handle;
  const data = await api('papers/' + handle); const paper = data.paper;
  byId('detail').hidden = false; text('paper-title', paper.bibliography.title || 'Title unavailable');
  text('bibliography', bib(paper)); text('identifiers', identifierLine(paper.identifiers));
  text('paper-sources', 'Sources: ' + (paper.sources.join(', ') || 'Not recorded'));
  byId('paper-status').replaceChildren(statusNodes(paper)); text('detail-evidence', evidenceLine(paper.evidence));
  text('abstract', paper.abstract || 'No abstract currently available. This does not imply exclusion.');
  const reps = byId('representations'); reps.replaceChildren();
  const controls = byId('document-controls'); controls.replaceChildren();
  for (const rep of paper.representations) {
    reps.append(node('p', rep.kind + ' — ' + rep.validity + (rep.readable ? ' — verified readable document body' : ' — not offered as trusted document-body text')));
    if (rep.readable) { const button = node('button', 'Read verified structured text'); button.onclick = () => readDocument(rep.handle).catch(failure); controls.append(button); }
  }
  if (!paper.representations.length) reps.append(node('p', 'No document representations preserved.'));
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
if (match) detail(match[1]).catch(failure);
else if (location.pathname === '/papers') catalogue().catch(failure);
else dashboard().catch(failure);
