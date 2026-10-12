'use strict';
// Durable workflows are kept separate from the original evidence navigation.
let investigation = localStorage.getItem('signalgraph-investigation') || 'demo';
let replayData,
  replayGeneration = 0,
  graphSelection = null,
  notificationTimer;
const orderedSources = () =>
  [...data.documents].sort(
    (a, b) => new Date(a.observed_at) - new Date(b.observed_at),
  );
const workspaceURL = (path) =>
  `${path}?workspace=${encodeURIComponent(investigation)}`;
async function requestJSON(path, payload) {
  const response = await fetch(
    path,
    payload === undefined
      ? {}
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ workspace: investigation, ...payload }),
        },
  );
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || `HTTP ${response.status}`);
  return result;
}
function notify(message, error = false) {
  $('#notification').textContent = message;
  $('#notification').classList.toggle('error', error);
  $('#notification').hidden = false;
  clearTimeout(notificationTimer);
  notificationTimer = setTimeout(
    () => {
      $('#notification').hidden = true;
    },
    error ? 9000 : 4000,
  );
}
async function refreshEvidence() {
  data = await requestJSON(workspaceURL('/api/snapshot'));
  render();
}
async function chooseInvestigation(id) {
  investigation = id;
  localStorage.setItem('signalgraph-investigation', id);
  graphSelection = null;
  selectedEntity = null;
  replayData = null;
  replayGeneration++;
  resetFilters();
  await load();
}
async function refreshWorkspaces() {
  const list = await requestJSON('/api/workspaces');
  $('#workspace-select').innerHTML = list
    .map((w) => `<option value="${esc(w.id)}">${esc(w.name)}</option>`)
    .join('');
  if (!list.some((w) => w.id === investigation)) {
    investigation = 'demo';
    localStorage.setItem('signalgraph-investigation', 'demo');
  }
  $('#workspace-select').value = investigation;
}
function renderWorkflows() {
  if (!data.workspace) return;
  $('#workspace-select').value = data.workspace.id;
  $('#data-label').textContent = data.synthetic
    ? 'SYNTHETIC DATA'
    : 'IMPORTED EVIDENCE';
  $('#workspace-mode').textContent = data.synthetic
    ? 'Synthetic investigation'
    : 'Imported investigation';
  $('#comparison-label').textContent = data.periods.join(' → ');
  $('#brief-heading').textContent =
    `${data.counts.conflict} conflicts. ${data.events.filter((e) => (e.review?.status ?? 'open') === 'open').length} signals to review.`;
  const meaningful = data.events.filter((e) => e.kind !== 'unverified');
  $('#brief-text').textContent = meaningful.length
    ? meaningful
        .slice(0, 4)
        .map((e) => `${entityName(e.entity_id)}: ${summary(e)}.`)
        .join(' ')
    : 'No additions, revisions, removals, or conflicts detected in this comparison. Missing evidence remains unverified.';
  $('#brief-coverage').textContent =
    `${data.documents.length} documents · ${data.entities.length} entities · ${data.workspace.name}`;
  $('#evidence-coverage').innerHTML = [
    ['Conflicting evidence', data.counts.conflict, 'conflict'],
    [
      'Observed changes',
      data.counts.addition + data.counts.revision + data.counts.removal,
      'revision',
    ],
    ['Unverified claims', data.counts.unverified, 'unverified'],
  ]
    .map(
      ([title, count, kind]) =>
        `<div class="coverage-item"><span><i class="legend ${kind}"></i>${title}</span><strong>${count}</strong></div>`,
    )
    .join('');
  const unread = (data.alerts ?? []).filter((a) => !a.seen).length;
  $('#workflow-summary').innerHTML =
    `<strong>${data.workspace.name ? esc(data.workspace.name) : 'Investigation'}</strong> · ${data.watches.length} watch rules · ${unread} unread alerts. Reviews and evidence are saved locally.`;
  $('#inbox-count').textContent = unread;
  $('#watch-entity').innerHTML =
    '<option value="">All entities</option>' +
    data.entities
      .map((e) => `<option value="${esc(e.id)}">${esc(e.name)}</option>`)
      .join('');
  renderBoard();
  renderWatches();
  const docsInOrder = orderedSources();
  $('#observed-slider').max = Math.max(0, docsInOrder.length - 1);
  if (!replayData) {
    $('#observed-slider').value = docsInOrder.length - 1;
    $('#valid-date').value = docsInOrder.at(-1).observed_at.slice(0, 10);
  }
  updateReplay();
  refreshWorkspaces().catch((error) => notify(error.message, true));
}
function renderBoard() {
  $('#review-board').innerHTML = [
    'open',
    'investigating',
    'resolved',
    'dismissed',
  ]
    .map((status) => {
      const events = data.events.filter(
        (e) => (e.review?.status ?? 'open') === status,
      );
      return `<section class="board-column"><h2>${pretty(status).toUpperCase()} / ${events.length}</h2>${events.map((e) => `<button class="board-card" data-event="${esc(e.id)}"><span class="badge ${e.kind}">${e.kind}</span><strong>${esc(eventTitle(e))}</strong><p>${esc(e.review?.note || summary(e))}</p></button>`).join('') || '<p class="muted">No signals here.</p>'}</section>`;
    })
    .join('');
}
function renderWatches() {
  const watches = new Map(data.watches.map((w) => [w.id, w]));
  const eventMap = new Map(data.events.map((e) => [e.id, e]));
  $('#watch-list').innerHTML =
    data.watches
      .map(
        (w) =>
          `<div class="watch-card"><div><strong>${esc(w.label)}</strong><small>${w.entity_id ? esc(entityName(w.entity_id)) : 'All entities'} · ${esc(w.kind)}</small></div><button class="text-button" data-remove-watch="${esc(w.id)}" aria-label="Remove watch ${esc(w.label)}">Remove</button></div>`,
      )
      .join('') ||
    '<p class="muted">Create a focused rule to start your local inbox.</p>';
  $('#alert-list').innerHTML =
    data.alerts
      .map((a) => {
        const e = eventMap.get(a.event_id),
          w = watches.get(a.watch_id);
        return `<div class="alert-card ${a.seen ? 'seen' : ''}"><strong>${esc(w?.label ?? 'Archived watch')}</strong><p>${e ? esc(eventTitle(e)) : 'Historical detection no longer present in current comparison'}</p><small class="muted">${a.seen ? 'Acknowledged' : 'Unread'} · ${date(a.created_at)}</small><div>${e ? `<button class="text-button" data-event="${esc(e.id)}">Inspect evidence →</button>` : ''}${a.seen ? '' : `<button class="text-button" data-ack-watch="${esc(a.watch_id)}" data-ack-event="${esc(a.event_id)}">Acknowledge</button>`}</div></div>`;
      })
      .join('') ||
    '<p class="muted">No matching alerts. Rules evaluate current detections and new appended evidence.</p>';
}
function decorateEvidence(event) {
  const r = event.review ?? { status: 'open', note: '', version: 0 };
  const diff = event.diff ?? [];
  const html = `<section class="diff-box"><p class="eyebrow">STATEMENT DIFF · BEFORE → AFTER</p>${diff.map((p) => (p.kind === 'removed' ? `<del>${esc(p.text)}</del>` : p.kind === 'added' ? `<ins>${esc(p.text)}</ins>` : `<span>${esc(p.text)}</span>`)).join(' ') || 'No statement text to compare.'}</section><section class="review-editor"><p class="eyebrow">ANALYST REVIEW · VERSION ${r.version}</p><p class="muted">Your decision annotates this signal. Original evidence and detection logic stay intact.</p><form id="review-form" data-event-id="${esc(event.id)}" data-version="${r.version}"><label>Decision<select id="review-status">${['open', 'investigating', 'resolved', 'dismissed'].map((s) => `<option value="${s}" ${s === r.status ? 'selected' : ''}>${pretty(s)}</option>`).join('')}</select></label><label>Notes / resolution rationale<textarea id="review-note" maxlength="4000">${esc(r.note)}</textarea></label><button type="submit" class="button">Save review</button><p id="review-save-status" class="mutation-status" role="status"></p></form><h3 class="eyebrow">REVIEW HISTORY</h3>${
    (data.history ?? [])
      .filter((h) => h.event_id === event.id)
      .map(
        (h) =>
          `<div class="history-row"><strong>${esc(h.status)} · version ${h.version}</strong><p>${esc(h.note)}</p><small class="muted">${esc(h.created_at)}</small></div>`,
      )
      .join('') || '<p class="muted">No analyst decisions recorded yet.</p>'
  }</section>`;
  $('#evidence-body').insertAdjacentHTML('beforeend', html);
}
async function updateReplay() {
  if (!data.workspace) return;
  const generation = ++replayGeneration;
  const source = orderedSources()[Number($('#observed-slider').value)];
  if (!source || !$('#valid-date').value) return;
  const valid = `${$('#valid-date').value}T12:00:00Z`;
  $('#observed-output').textContent =
    `${date(source.observed_at)} · ${source.observed_at}`;
  $('#valid-output').textContent = `${date(valid)} · 12:00 UTC`;
  $('#replay-summary').textContent = 'Reconstructing from observed evidence…';
  try {
    const result = await requestJSON(
      `${workspaceURL('/api/replay')}&observed_until=${encodeURIComponent(source.observed_at)}&valid_at=${encodeURIComponent(valid)}`,
    );
    if (generation !== replayGeneration) return;
    replayData = result;
    $('#replay-summary').textContent =
      `${result.document_count} known documents · ${result.known_claim_count} observed assertions · ${result.active_claim_count} active assertions · ${result.conflicts.length} conflicts at this date`;
    $('#replay-rows').innerHTML =
      result.claims
        .map(
          (c) =>
            `<tr><td>${esc(entityName(c.entity_id))}<br><span class="muted">${esc(pretty(c.predicate))}</span></td><td>${esc(c.value)}</td><td><span class="claim-state ${esc(c.status)}">${esc(c.status)}${c.retired_by.length ? ` · ${esc(c.retired_by.join(', '))}` : ''}</span></td><td><button data-source="${esc(c.source_id)}">${esc(c.source_id)} →</button></td></tr>`,
        )
        .join('') ||
      '<tr><td colspan="4">No evidence was known at this observation date.</td></tr>';
    if (location.hash === '#graph') renderGraph();
  } catch (error) {
    if (generation === replayGeneration)
      $('#replay-summary').textContent = error.message;
  }
}
function renderGraph() {
  if (!data?.workspace) return;
  const width = 650,
    height = 430,
    centerX = 325,
    centerY = 215;
  const nodes = data.entities.map((e, i) => ({
    ...e,
    x:
      centerX +
      215 * Math.cos((2 * Math.PI * i) / data.entities.length - Math.PI / 2),
    y:
      centerY +
      150 * Math.sin((2 * Math.PI * i) / data.entities.length - Math.PI / 2),
  }));
  const positions = new Map(nodes.map((n) => [n.id, n]));
  let relationships = data.relationships;
  if ($('#graph-scope').value === 'active')
    relationships = (replayData?.relationships ?? []).map((c) => ({
      source: c.entity_id,
      target: c.target_id,
      predicate: c.predicate,
      claim_id: c.id,
      source_id: c.source_id,
    }));
  const lines = relationships
    .filter((r) => positions.has(r.source) && positions.has(r.target))
    .map((r) => {
      const a = positions.get(r.source),
        b = positions.get(r.target);
      return `<line class="graph-edge ${r.retracted ? 'retracted' : ''}" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"><title>${r.retracted ? 'Retraction evidence: ' : ''}${esc(entityName(r.source))} → ${esc(r.predicate)} → ${esc(entityName(r.target))} (${esc(r.source_id)})</title></line>`;
    })
    .join('');
  $('#graph-canvas').innerHTML =
    `<svg viewBox="0 0 ${width} ${height}" aria-label="Sourced entity relationship graph">${lines}${nodes
      .map((n) => {
        const events = data.events.filter((e) => e.entity_id === n.id),
          conflicting = events.some((e) => e.kind === 'conflict');
        return `<g class="graph-node ${conflicting ? 'conflict' : ''} ${graphSelection === n.id ? 'selected' : ''}" tabindex="0" role="button" aria-label="Investigate ${esc(n.name)}, ${events.length} signals" data-graph-node="${esc(n.id)}" transform="translate(${n.x},${n.y})"><circle r="29"></circle><text text-anchor="middle" dy="5">${esc(
          n.name
            .split(' ')
            .map((s) => s[0])
            .slice(0, 2)
            .join(''),
        )}</text><text text-anchor="middle" y="49">${esc(n.name)}</text><text class="node-count" text-anchor="middle" y="65">${events.length} signals</text></g>`;
      })
      .join('')}</svg>`;
  const id = graphSelection,
    node = entities.get(id);
  const linked = relationships.filter(
    (r) => r.source === id || r.target === id,
  );
  $('#graph-detail').innerHTML = node
    ? `<p class="eyebrow">${esc(node.kind)} / ${esc(node.id)}</p><h2>${esc(node.name)}</h2><p class="muted">${esc(node.aliases.join(', ') || 'No aliases')}</p><h3 class="eyebrow">SOURCED RELATIONSHIPS</h3>${linked.map((r) => `<div class="graph-link-row">${r.retracted ? 'Retraction evidence · ' : ''}${esc(entityName(r.source))} → ${esc(pretty(r.predicate))} → ${esc(entityName(r.target))}<br><button class="text-button" data-source="${esc(r.source_id)}">${esc(r.source_id)} · read evidence →</button></div>`).join('') || '<p class="muted">No relationships in this scope.</p>'}<h3 class="eyebrow">SIGNALS</h3>${
        data.events
          .filter((e) => e.entity_id === id)
          .map(eventRow)
          .join('') || '<p class="muted">No detections for this entity.</p>'
      }<button class="text-button" data-open-entity="${esc(id)}">Open all entity assertions →</button>`
    : '<p class="eyebrow">FOLLOW THE EVIDENCE</p><h2>An investigation, connected.</h2><p class="muted">Choose a node to inspect its signals and source-linked relationships. Rose nodes have conflicting assertions. No relationships are inferred.</p><p class="muted">Use Temporal replay to set the two dates, then select “Active at replay dates” to filter edges.</p>';
}
async function downloadFile(path, filename) {
  const response = await fetch(workspaceURL(path));
  if (!response.ok) throw new Error(`Export failed: HTTP ${response.status}`);
  const url = URL.createObjectURL(await response.blob()),
    link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
$('#workspace-select').addEventListener('change', (e) =>
  chooseInvestigation(e.target.value),
);
$('#observed-slider').addEventListener('input', updateReplay);
$('#valid-date').addEventListener('change', updateReplay);
$('#graph-scope').addEventListener('change', renderGraph);
document.addEventListener('keydown', (event) => {
  const node = event.target.closest('[data-graph-node]');
  if (node && ['Enter', ' '].includes(event.key)) {
    event.preventDefault();
    graphSelection = node.dataset.graphNode;
    renderGraph();
    [...document.querySelectorAll('[data-graph-node]')]
      .find((n) => n.dataset.graphNode === graphSelection)
      ?.focus();
  }
});
document.addEventListener('click', async (event) => {
  const graphNode = event.target.closest('[data-graph-node]');
  if (graphNode) {
    graphSelection = graphNode.dataset.graphNode;
    renderGraph();
    return;
  }
  const button = event.target.closest('button');
  if (!button) return;
  try {
    if (button.id === 'open-import') {
      $('#import-status').textContent = '';
      $('#import-dialog').showModal();
      $('#import-name').focus();
    }
    if (button.id === 'close-import') $('#import-dialog').close();
    if (button.id === 'load-template')
      $('#import-json').value = JSON.stringify(
        await requestJSON(workspaceURL('/api/dataset')),
        null,
        2,
      );
    if (button.id === 'download-dataset')
      await downloadFile('/api/dataset', 'signalgraph-dataset.json');
    if (button.id === 'download-briefing')
      await downloadFile('/api/briefing', 'signalgraph-briefing.md');
    if (button.id === 'graph-reset') {
      graphSelection = null;
      renderGraph();
    }
    if (button.dataset.openEntity) {
      renderEntity(button.dataset.openEntity);
      location.hash = 'entities';
    }
    if (button.dataset.removeWatch) {
      await requestJSON('/api/watch/remove', {
        id: button.dataset.removeWatch,
      });
      await refreshEvidence();
      notify('Watch removed.');
    }
    if (button.dataset.ackWatch) {
      await requestJSON('/api/alert/acknowledge', {
        watch_id: button.dataset.ackWatch,
        event_id: button.dataset.ackEvent,
      });
      await refreshEvidence();
      notify('Alert acknowledged.');
    }
  } catch (error) {
    notify(error.message, true);
  }
});
$('#import-file').addEventListener('change', async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 4 * 1024 * 1024) {
    $('#import-status').textContent = 'File exceeds the 4 MiB limit.';
    return;
  }
  $('#import-json').value = await file.text();
});
$('#import-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  $('#import-status').textContent =
    'Validating every source, timestamp, and claim…';
  try {
    const payload = {
      name: $('#import-name').value,
      dataset: JSON.parse($('#import-json').value),
    };
    const append = $('#import-action').value === 'append';
    const result = await requestJSON(
      append ? '/api/append' : '/api/import',
      payload,
    );
    $('#import-dialog').close();
    replayData = null;
    await refreshWorkspaces();
    await chooseInvestigation(result.workspace);
    notify(
      append
        ? 'Evidence appended. Watch alerts refreshed.'
        : 'Investigation imported and saved locally.',
    );
  } catch (error) {
    $('#import-status').textContent = error.message;
  } finally {
    submit.disabled = false;
  }
});
$('#watch-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const submit = event.submitter;
  submit.disabled = true;
  try {
    await requestJSON('/api/watch', {
      label: $('#watch-label').value,
      entity_id: $('#watch-entity').value || null,
      kind: $('#watch-kind').value,
    });
    $('#watch-label').value = '';
    await refreshEvidence();
    notify('Watch created. Matching detections are in the inbox.');
  } catch (error) {
    notify(error.message, true);
  } finally {
    submit.disabled = false;
  }
});
document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'review-form') return;
  event.preventDefault();
  const form = event.target,
    submit = event.submitter;
  submit.disabled = true;
  try {
    await requestJSON('/api/review', {
      event_id: form.dataset.eventId,
      status: $('#review-status').value,
      note: $('#review-note').value,
      version: Number(form.dataset.version),
    });
    await refreshEvidence();
    showEvent(form.dataset.eventId);
    notify('Review saved. Evidence preserved.');
  } catch (error) {
    $('#review-save-status').textContent = error.message;
    $('#review-save-status').classList.add('error');
  } finally {
    if (submit.isConnected) submit.disabled = false;
  }
});
window.workbench = {
  snapshotURL: () => workspaceURL('/api/snapshot'),
  render: renderWorkflows,
  renderGraph,
  decorateEvidence,
};
refreshWorkspaces()
  .then(() => load())
  .catch((error) => {
    notify(error.message, true);
    load();
  });
