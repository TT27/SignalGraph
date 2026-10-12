# SignalGraph Lite — morning review

Prepared 13 October 2026 (Australia/Sydney). Work is committed on `feature/signalgraph-lite`, based on upstream `0a3b1711b018e5590cf5c44a3ee3e67d6733ee13`. The user has now authorized committing and pushing this feature branch to `TT27/SignalGraph`. No deployment or PR is included.

## Completed

- Self-contained `examples/signalgraph_lite`, with no Graphiti core or root dependency-manifest changes.
- Immutable typed source/entity/claim/event models, timezone validation, independent observation/validity timestamps, exact excerpt provenance, and explicit relationship targets.
- Deterministic offline fixture: **12 documents, 6 entities, 13 assertions, 8 detections**. Four changes (two revisions, one addition, one explicit removal), two contradictions, two unverified claims.
- Rules preserve ambiguity, distinguish temporal revisions from overlapping conflicts, and refuse to infer removal from missing evidence. Explicit supersessions preserve original evidence while retiring conflict candidates.
- Responsive dark workspace: overview, search and filters, chronological publication timeline with slider, entity/relationship explorer, source library, evidence drawer, JSON export, loading/empty/error/retry states.
- Optional supported Graphiti episode ingestion adapter, explicitly **externally unverified**, with no silent offline fallback.
- Project README, exact startup commands, architecture/tradeoffs, measured labelled evaluation, browser smoke script, screenshots, and 60-second showcase script.

## Run

From the repository root, Python 3.10+:

```bash
python -m examples.signalgraph_lite.server
```

Open **http://127.0.0.1:8765**. No install, credentials, Neo4j, model service, or internet required. Alternative port: `--port 8766`. Ctrl+C stops it.

```bash
python -m unittest discover -s examples/signalgraph_lite/tests -p 'test_*.py' -v
python -m examples.signalgraph_lite.evaluate
```

Developer and browser commands are in [the project README](examples/signalgraph_lite/README.md). Root pytest imports database fixtures; use the documented isolated pytest command for this example.

## Validation results

| Gate | Result |
|---|---|
| Isolated pytest 9.1.1 | **25 passed**, 0 failed |
| Dependency-free unittest | **25 passed**, 0 failed |
| Ruff 0.17.0 lint + format check | Passed, 11 Python files formatted |
| Pyright 1.1.414 | Passed, 0 errors/warnings, including optional adapter API usage |
| JavaScript `node --check` | Passed |
| Chromium / Playwright 1.62.0 | Passed: all navigation, conflict/entity/search filters, exact excerpts, Escape/focus return, timeline slider, entity relationships, source drawer, export, mobile overflow, HTTP error retry, empty fixture |
| Fixture exact-match evaluation | 8 expected / 8 predicted / 8 TP / 0 FP / 0 FN; **precision 1.0, recall 1.0** |
| Graphiti real database / LLM ingestion | **Unverified**; no credentials or services used |
| Upstream full core suite / root make gates | **Not run**; no core changes, example gates isolated from database/optional dependencies |

Evaluation labels were authored for the fixture, not obtained from the detector. The result is a small structured synthetic regression measurement, **not real-world accuracy**. Tests include shared aliases, unknown identities, timezone offsets, half-open boundaries, reversed observation/validity order, invalid supersession timestamps, explicit retraction, absent evidence, shuffled inputs, invented quotations, and HTTP failures.

Screenshots are real browser captures, not design mockups:

- [Desktop overview](examples/signalgraph_lite/screenshots/overview.png) — 1440×1080 viewport, full page.
- [Evidence drawer](examples/signalgraph_lite/screenshots/evidence.png) — exact source quotations and dates.
- [Mobile overview](examples/signalgraph_lite/screenshots/mobile.png) — 390×844 viewport, full page.

## Assumptions and limitations

The fixtures already contain structured assertions; no arbitrary prose extraction is claimed. All compared attributes are single-valued and predicates canonical. Values normalize case/whitespace without numeric units or semantic inference. Aliases require unique matches or explicit IDs. Explicit correction links are treated as authoritative dataset annotations; source trust/adjudication is not implemented. Pairwise conflict detection is suitable for this small dataset.

Timeline navigation shows source publication history and final two-period detections; it does not claim an as-of reconstruction. Historical relationships are presented as source assertions and can be explicitly retracted. Missing current evidence is labelled unverified, even if an earlier validity window has ended. Fixture URIs are local authored sources, never invented external citations.

The Graphiti adapter only ingests real episodes through supported APIs. It does not yet map returned graph edges into the comparison engine, guarantee extraction of supplied validity windows, or offer repeated-ingest idempotency. Real integration testing is required before production use. The demo HTTP server is loopback-only and deliberately small; it is not a multi-user production service.

Initial repository cloning and package installation failed because network access had not been enabled for the shell. Retrying with the permitted network capability succeeded. The completed work is in the actual upstream clone, not the temporary standalone scaffold. No outstanding external blocker remains for the offline MVP.

## Remaining work and best next enhancements

1. **Graphiti round-trip integration:** map episode IDs and temporal graph edges to deterministic comparison inputs; verify exact provenance and validity in a real Neo4j/mock-model test environment, then add idempotent ingest.
2. **Broader evaluation and adjudication:** add independently labelled cases with multi-valued facts, competing corrections, numeric/unit normalization and source reliability; report precision/recall by class on held-out data.
3. **True temporal investigation:** implement observation-time as-of snapshots, retained resolution history, and a navigable entity graph with validity-aware relationship filtering.

The offline MVP is complete and reviewable on `feature/signalgraph-lite` in the SignalGraph fork once pushed. The authorized delivery adds the example and this review document; Graphiti core and the main branch are unchanged. Deployment or a PR still requires separate explicit approval.
