'use strict';
const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? '').replace(
    /[&<>"']/g,
    (c) =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[
        c
      ],
  );
const pretty = (value) => String(value).replaceAll('_', ' ');
const date = (value) =>
  value
    ? new Date(value).toLocaleDateString('en-GB', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        timeZone: 'UTC',
      })
    : 'Open-ended';
const symbols = {
  conflict: '≠',
  revision: '↻',
  addition: '+',
  removal: '−',
  unverified: '?',
};
const titles = {
  overview: 'Overview',
  changes: 'Changes & contradictions',
  timeline: 'Source timeline',
  entities: 'Entity explorer',
  sources: 'Source library',
  about: 'About SignalGraph Lite',
};
const descriptions = {
  overview:
    'A traceable view of company claims, changes, and conflicting evidence.',
  changes:
    'Follow every detection back to its source. Filter by entity and evidence type.',
  timeline:
    'Explore what was observed, when it appeared, and which assertions changed.',
  entities:
    'Trace entity identities, relationships, and the claims that connect them.',
  sources: 'Inspect the original announcements behind this investigation.',
  about:
    'An independently runnable, evidence-led temporal intelligence example.',
};
let data, docs, claims, entities, lastFocus, selectedEntity;
const entityName = (id) => entities.get(id)?.name ?? 'Ambiguous “Nova”';
function eventTitle(event) {
  return `${entityName(event.entity_id)} · ${pretty(event.predicate)}`;
}
function summary(event) {
  const before = event.before.map((id) => claims.get(id).value).join(', ');
  const after = event.after.map((id) => claims.get(id).value).join(', ');
  if (event.kind === 'unverified')
    return event.classification === 'Ambiguous identity'
      ? 'Shared alias needs identity resolution'
      : 'No current-period evidence to verify this assertion';
  if (event.kind === 'addition') return `Newly observed: ${after}`;
  if (event.kind === 'removal') return `Explicitly retracted: ${before}`;
  return `${before} → ${after}${event.kind === 'conflict' ? ' · overlapping validity' : ''}`;
}
function eventRow(event) {
  return `<button class="event-row" data-event="${esc(event.id)}" aria-label="Inspect ${esc(event.kind)}: ${esc(eventTitle(event))}"><span class="event-icon ${event.kind}" aria-hidden="true">${symbols[event.kind]}</span><span class="event-content"><strong>${esc(eventTitle(event))}</strong><small>${esc(summary(event))}</small></span><span class="badge ${event.kind}">${esc(pretty(event.kind))}</span><span class="event-date">${date(event.observed_at)}</span><span class="row-arrow" aria-hidden="true">→</span></button>`;
}
function navigate() {
  if (!data) return;
  const requested = location.hash.slice(1) || 'overview';
  const view = Object.hasOwn(titles, requested) ? requested : 'overview';
  document.querySelectorAll('.view').forEach((section) => {
    section.hidden = section.id !== `view-${view}`;
  });
  document.querySelectorAll('nav a').forEach((link) => {
    const active = link.dataset.view === view;
    link.classList.toggle('active', active);
    if (active) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  });
  $('#breadcrumb').textContent = titles[view];
  $('#page-title').innerHTML =
    view === 'overview'
      ? 'See what changed.<br><span class="muted-title">Understand why it matters.</span>'
      : esc(titles[view]);
  $('#page-description').textContent = descriptions[view];
  document.title = `${titles[view]} · SignalGraph Lite`;
}
function renderChanges() {
  const query = $('#search').value.trim().toLowerCase(),
    kind = $('#kind-filter').value,
    entity = $('#entity-filter').value;
  const matches = data.events.filter(
    (event) =>
      (kind === 'all' || kind === event.kind) &&
      (entity === 'all' || entity === (event.entity_id ?? 'unknown')) &&
      `${eventTitle(event)} ${event.explanation} ${summary(event)}`
        .toLowerCase()
        .includes(query),
  );
  $('#result-count').textContent =
    `${matches.length} of ${data.events.length} detections · Exact source provenance available`;
  $('#changes-list').innerHTML = matches.length
    ? matches.map(eventRow).join('')
    : '<div class="empty"><strong>No matching detections</strong><p>Try another search or reset your filters.</p><button class="button" data-reset>Reset filters</button></div>';
}
function resetFilters() {
  $('#search').value = '';
  $('#kind-filter').value = 'all';
  $('#entity-filter').value = 'all';
  renderChanges();
}
function renderTimeline() {
  const ordered = [...data.documents].sort(
    (a, b) => new Date(a.observed_at) - new Date(b.observed_at),
  );
  const limit = Number($('#date-range').value);
  $('#date-output').textContent =
    `${date(ordered[limit].observed_at)} · ${limit + 1}/${ordered.length} documents`;
  $('#timeline-list').innerHTML = ordered
    .slice(0, limit + 1)
    .reverse()
    .map((doc) => {
      const events = data.events.filter(
        (e) =>
          e.observed_at === doc.observed_at && e.source_ids.includes(doc.id),
      );
      return `<section class="timeline-day"><h2>${date(doc.observed_at)} <span class="muted">/ ${esc(doc.period)}</span></h2><div class="timeline-source"><strong>${esc(doc.title)}</strong><p>${esc(doc.publisher)} · ${esc(doc.id)} · Synthetic source</p>${events.map(eventRow).join('')}${events.length ? '' : '<p>Baseline evidence recorded; no change at this observation.</p>'}<button class="text-button" data-source="${esc(doc.id)}">Read original document →</button></div></section>`;
    })
    .join('');
}
function renderEntity(id) {
  selectedEntity = id;
  const entity = entities.get(id);
  document.querySelectorAll('.entity-button').forEach((button) => {
    const active = button.dataset.entity === id;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
  const relevant = data.claims.filter((c) => resolve(c.entity) === id);
  const relations = data.relationships.filter(
    (r) => r.source === id || r.target === id,
  );
  $('#entity-detail').innerHTML =
    `<p class="eyebrow">${esc(entity.kind)} / ${esc(entity.id)}</p><h2>${esc(entity.name)}</h2><p class="entity-meta">Known aliases: ${esc(entity.aliases.join(', ') || 'None')}<br>Shared aliases never merge entities automatically.</p><p class="eyebrow">RELATIONSHIPS · SOURCE ASSERTIONS</p>${relations.length ? relations.map((r) => `<div class="relationship"><button data-entity="${esc(r.source)}">${esc(entityName(r.source))}</button><span>→ ${esc(pretty(r.predicate))} →</span><button data-entity="${esc(r.target)}">${esc(entityName(r.target))}</button><small>${r.retracted ? 'Retracted assertion' : 'Source assertion'} · ${date(r.valid_from)}</small><button class="text-button" data-source="${esc(r.source_id)}">${esc(r.source_id)} →</button></div>`).join('') : '<p class="muted">No relationships asserted in this fixture.</p>'}<div class="entity-claims"><p class="eyebrow">ALL ASSERTIONS · ${relevant.length}</p>${relevant.length ? relevant.map((c) => `<div class="claim-card"><p>${esc(pretty(c.predicate))} <span class="muted">/</span> <strong>${esc(c.value)}</strong></p><small>Valid: ${date(c.valid_from)} → ${date(c.valid_to)} ${c.supersedes ? '· supersedes ' + esc(c.supersedes) : ''}</small><button data-source="${esc(c.source_id)}">View ${esc(c.source_id)} · ${esc(docs.get(c.source_id).title)} →</button></div>`).join('') : '<p class="muted">No direct assertions; this entity appears as a relationship target.</p>'}</div>`;
}
function resolve(name) {
  if (entities.has(name)) return name;
  const normalized = name.trim().replace(/\s+/g, ' ').toLowerCase();
  const matches = data.entities.filter((e) =>
    [e.name, ...e.aliases].some(
      (a) => a.trim().replace(/\s+/g, ' ').toLowerCase() === normalized,
    ),
  );
  return matches.length === 1 ? matches[0].id : null;
}
function showDrawer(html) {
  lastFocus = document.activeElement;
  $('#evidence-body').innerHTML = html;
  $('#evidence').showModal();
  $('#close-drawer').focus();
}
function evidenceBlock(id, label) {
  const c = claims.get(id),
    d = docs.get(c.source_id);
  return `<section class="evidence-block"><h3>${esc(label)} / ${esc(c.id)}</h3><div class="value">${esc(c.value)}</div><blockquote>“${esc(c.quote)}”</blockquote><dl><dt>Source</dt><dd>${esc(d.id)} · ${esc(d.title)}</dd><dt>Publisher</dt><dd>${esc(d.publisher)}</dd><dt>Observed</dt><dd>${esc(d.observed_at)}</dd><dt>Valid from</dt><dd>${esc(c.valid_from)}</dd><dt>Valid until</dt><dd>${esc(c.valid_to ?? 'Open-ended (not proof of continued truth)')}</dd><dt>Provenance</dt><dd>${esc(d.uri)}</dd></dl><button class="text-button" data-source="${esc(d.id)}">Read full source →</button></section>`;
}
function showEvent(id) {
  const e = data.events.find((event) => event.id === id);
  if (!e) return;
  const absentBefore =
    '<div class="evidence-block"><h3>BEFORE</h3><p class="muted">No linked baseline assertion. This does not establish that the fact was previously false.</p></div>';
  const absentAfter =
    '<div class="evidence-block"><h3>AFTER</h3><p class="muted">No later-period source. Continued validity is unverified.</p></div>';
  const html = `<span class="badge ${e.kind}">${esc(e.kind)}</span><h2 id="evidence-title">${esc(eventTitle(e))}</h2><p class="explanation">${esc(e.explanation)}</p>${e.before.length ? e.before.map((id) => evidenceBlock(id, 'Before')).join('') : absentBefore}${e.after.length ? e.after.map((id) => evidenceBlock(id, 'After')).join('') : absentAfter}<p class="uncertainty">Evidence classification: ${esc(e.classification)}. No numerical confidence estimate.</p><p class="pill-note">Synthetic fixture · Observed dates and validity dates are independent · ${esc(e.id)}</p>`;
  if ($('#evidence').open) $('#evidence-body').innerHTML = html;
  else showDrawer(html);
}
function showSource(id) {
  const doc = docs.get(id);
  if (!doc) return;
  const related = data.events.filter((e) => e.source_ids.includes(id));
  const html = `<span class="badge">Synthetic source</span><h2 id="evidence-title">${esc(doc.title)}</h2><p class="muted">${esc(doc.publisher)} · ${esc(doc.id)}</p><section class="evidence-block"><h3>PROVENANCE</h3><dl><dt>Observed</dt><dd>${esc(doc.observed_at)}</dd><dt>Period</dt><dd>${esc(doc.period)}</dd><dt>Local URI</dt><dd>${esc(doc.uri)}</dd></dl></section><h3 class="eyebrow">VERBATIM DOCUMENT</h3><div class="source-body">${esc(doc.body)}</div><p class="pill-note">This is an authored demo document. It is not an external citation.</p><h3 class="eyebrow">LINKED DETECTIONS</h3>${related.length ? related.map(eventRow).join('') : '<p class="muted">No detections linked to this document.</p>'}`;
  if ($('#evidence').open) $('#evidence-body').innerHTML = html;
  else showDrawer(html);
}
function render() {
  docs = new Map(data.documents.map((d) => [d.id, d]));
  claims = new Map(data.claims.map((c) => [c.id, c]));
  entities = new Map(data.entities.map((e) => [e.id, e]));
  const changed =
    data.counts.revision + data.counts.addition + data.counts.removal;
  const metrics = [
    [
      'Source documents',
      data.documents.length,
      'Verbatim, traceable announcements',
      '▤',
      '',
    ],
    [
      'Entities tracked',
      data.entities.length,
      'Explicit identity & alias resolution',
      '◇',
      '',
    ],
    [
      'Meaningful changes',
      changed,
      'Addition · revision · removal',
      '⇄',
      'change',
    ],
    [
      'Unresolved conflicts',
      data.counts.conflict,
      'Overlapping validity, different values',
      '≠',
      'conflict',
    ],
  ];
  $('#metrics').innerHTML = metrics
    .map(
      ([label, count, note, icon, cls]) =>
        `<div class="metric ${cls}"><div class="metric-label">${label}<span aria-hidden="true">${icon}</span></div><strong>${count}</strong><small>${note}</small></div>`,
    )
    .join('');
  $('#nav-count').textContent = data.events.length;
  $('#priority-list').innerHTML = data.events
    .filter((e) => e.kind !== 'unverified')
    .sort((a, b) => (a.kind !== 'conflict') - (b.kind !== 'conflict'))
    .slice(0, 4)
    .map(eventRow)
    .join('');
  $('#entity-filter').innerHTML += data.entities
    .map((e) => `<option value="${esc(e.id)}">${esc(e.name)}</option>`)
    .join('');
  $('#entity-list').innerHTML = data.entities
    .map(
      (e) =>
        `<button class="entity-button" data-entity="${esc(e.id)}"><span class="entity-avatar">${esc(
          e.name
            .split(' ')
            .map((n) => n[0])
            .slice(0, 2)
            .join(''),
        )}</span><span>${esc(e.name)}<small>${esc(e.kind)} · ${esc(e.id)}</small></span></button>`,
    )
    .join('');
  $('#source-list').innerHTML = data.documents
    .map(
      (d) =>
        `<article class="panel source-card"><small>${esc(d.id)} / ${esc(d.period.toUpperCase())}</small><h2>${esc(d.title)}</h2><p>${esc(d.publisher)} · ${date(d.observed_at)}</p><p class="source-excerpt">${esc(d.body)}</p><button class="text-button" data-source="${esc(d.id)}">Inspect provenance →</button></article>`,
    )
    .join('');
  $('#date-range').max = data.documents.length - 1;
  $('#date-range').value = data.documents.length - 1;
  renderChanges();
  renderTimeline();
  renderEntity(selectedEntity ?? data.entities[0].id);
  navigate();
  $('#state').hidden = true;
  $('#app').hidden = false;
}
async function load() {
  $('#state').hidden = false;
  $('#app').hidden = true;
  $('#state').textContent = 'Loading evidence and comparing periods…';
  try {
    const response = await fetch('/api/snapshot', {
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok)
      throw new Error(`Local engine returned HTTP ${response.status}`);
    data = await response.json();
    if (data.mode !== 'offline-demo' || !Array.isArray(data.events))
      throw new Error('Unexpected engine response');
    if (!data.documents.length || !data.entities.length) {
      $('#state').innerHTML =
        '<h2>No investigation data</h2><p>Add documents and entities to the local fixture, then reload.</p><button class="button" data-retry>Reload fixture</button>';
      return;
    }
    render();
  } catch (error) {
    $('#state').innerHTML =
      `<h2>Evidence could not be loaded</h2><p>${esc(error.message)}</p><p>Check that the local Python server is running and the fixture is valid.</p><button class="button" data-retry>Try again</button>`;
  }
}
document.addEventListener('click', (event) => {
  const button = event.target.closest('button');
  if (!button) return;
  if (button.dataset.event) showEvent(button.dataset.event);
  if (button.dataset.source) showSource(button.dataset.source);
  if (button.dataset.entity) renderEntity(button.dataset.entity);
  if (button.dataset.go) location.hash = button.dataset.go;
  if (button.hasAttribute('data-reset') || button.id === 'reset')
    resetFilters();
  if (button.hasAttribute('data-retry')) load();
  if (button.id === 'close-drawer') $('#evidence').close();
  if (button.id === 'export') {
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }),
    );
    const link = document.createElement('a');
    link.href = url;
    link.download = 'signalgraph-evidence.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
});
$('#evidence').addEventListener('close', () => {
  if (lastFocus?.isConnected) lastFocus.focus();
});
$('#evidence').addEventListener('click', (event) => {
  if (event.target === $('#evidence')) {
    const box = event.target.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right)
      event.target.close();
  }
});
$('#search').addEventListener('input', renderChanges);
$('#kind-filter').addEventListener('change', renderChanges);
$('#entity-filter').addEventListener('change', renderChanges);
$('#date-range').addEventListener('input', renderTimeline);
window.addEventListener('hashchange', navigate);
load();
