# SignalGraph Desk — delivery review

Prepared 13 October 2026 (Australia/Sydney). The original SignalGraph Lite demo has become **SignalGraph Desk**, a local evidence investigation workbench. Delivery remains on `feature/signalgraph-lite` in [TT27/SignalGraph](https://github.com/TT27/SignalGraph/tree/feature/signalgraph-lite), with automatic commits and push authorized by the user. No deployment, main-branch merge or PR is included.

## Purpose

Help researchers and analysts follow changing company/vendor claims from original evidence to an explainable decision. The tool distinguishes source observation time from asserted validity, makes contradictions visible, stores investigation work, and produces a source-linked handoff briefing. It supports a working offline showcase and real user-supplied structured evidence.

## New capabilities

- **Your own investigations:** validated JSON/file imports create isolated SQLite investigations. A project switcher persists the selection. Synthetic provenance is explicit per document; imported evidence never silently becomes demo data.
- **Immutable evidence append:** identical records are idempotent; changed existing IDs fail atomically. New evidence recomputes detections and watch matches. The built-in demo remains fixed.
- **Two-clock replay:** independently choose evidence observed by a date and claims valid at a date. Later publications cannot leak into earlier knowledge. Original historical assertions remain visible before a known correction takes effect.
- **Evidence graph:** keyboard-selectable entity nodes, conflict highlighting, explicitly sourced historical relationships, visibly dashed retractions, and edges active at replay dates. No inferred relationships.
- **Review workflow:** open/investigating/resolved/dismissed board, rationale for resolution/dismissal, persistent notes, append-only application history, and optimistic version checks against stale updates. Review decisions do not rewrite detected evidence.
- **Focused watches:** entity/type rules, a deduplicated local alert inbox, persisted acknowledgement, and newly matching alerts after append. No external polling or messages.
- **Shareable output:** word-level evidence diffs, source text SHA-256 fingerprints, deterministic Markdown briefing with original quotations/review notes/manifest, JSON evidence export and raw dataset download.
- **Professional interface:** all summaries computed from selected evidence, explicit synthetic/imported labels, responsive workflows and recovery states.
- **Research and engineering:** primary-source comparison of changedetection.io, OpenCTI, Datasette, Cytoscape.js and Graphiti; maintained original stack; dedicated GitHub Actions workflow for offline gates and disposable browser tests.

[RESEARCH.md](examples/signalgraph_lite/RESEARCH.md) explains which patterns informed the application and what was deliberately left outside its implemented scope. No other project's code/assets were copied. Graphiti core and upstream dependencies remain unchanged. The root README now introduces the fork application while retaining upstream documentation; Git ignores the default local database directory.

## Run

```bash
git clone --branch feature/signalgraph-lite https://github.com/TT27/SignalGraph.git
cd SignalGraph
python -m examples.signalgraph_lite.server
```

Open **http://127.0.0.1:8765**. Python 3.10+; no install, API key, external LLM, Neo4j or internet required. Default persistence: `work/signalgraph/workspace.sqlite3`. Stop with Ctrl+C; use `--port`/`--db` for another port/database. Copy the SQLite file while stopped to back it up.

[App README](examples/signalgraph_lite/README.md) contains exact schema, append rules, architecture, API and test commands. [WALKTHROUGH.md](examples/signalgraph_lite/WALKTHROUGH.md) provides a 60-second demonstration.

## Validation

| Check | Result |
|---|---|
| Offline pytest | **60 passing tests** |
| Ruff lint + canonical Python format | Passed |
| Pyright | Passed, including adapter API usage |
| JavaScript syntax (both scripts) | Passed |
| Disposable full browser workflow | Passed: import validation/isolation, append, reload persistence, two clocks, graph scopes, review history, watch/acknowledgement, briefing export and mobile layouts |
| Original browser workflow | Navigation, filters, source drawer, keyboard dismissal/focus, timeline, JSON export, mobile, empty state and error retry checked separately |
| Labelled synthetic evaluation | 8 expected, 8 predicted, 8 TP, 0 FP/FN; precision **1.0**, recall **1.0** |
| Remote CI | Workflow added; remote execution results should be read in GitHub Actions after push |
| Real Graphiti database/model round trip | **Externally unverified** |
| Upstream root/core/database suites | Not run; core implementation unchanged and app checks isolated |

The fixture score is a small regression measurement, not real-world accuracy. New tests establish temporal and persistence correctness: no future evidence, half-open windows, timezone offsets, correction effective dates, immutable append/rollback, restart behavior, duplicate alerts, review concurrency, explicit source classification, bounded import validation, exact source hashes and safe literal Markdown quotations.

## Real screenshots

Captured with Chromium/Playwright using disposable local data, at 1440×1080 desktop and 390×844 mobile viewports:

- [Overview](examples/signalgraph_lite/screenshots/overview.png)
- [Temporal replay](examples/signalgraph_lite/screenshots/replay.png)
- [Evidence graph](examples/signalgraph_lite/screenshots/graph.png)
- [Evidence and analyst review](examples/signalgraph_lite/screenshots/evidence.png)
- [Watch inbox](examples/signalgraph_lite/screenshots/watches.png)
- [Mobile](examples/signalgraph_lite/screenshots/mobile.png)

Browser test data is isolated in temporary databases, not the user's workspace. No credentials, real user data or local SQLite databases are committed.

## Practical limits

Input claims are analyst-labelled structured assertions. The tool does not extract facts from raw prose, authenticate source publishers, score trust, prove truth, convert numeric units or support multi-valued predicates. Hashes identify stored text only. Explicit correction links are trusted input annotations; competing authoritative corrections require analyst judgment.

The comparison view covers two periods. Replay uses independent observation/validity instants; the browser's validity day is noon UTC, while the API accepts a full instant. Review history is durable application history, not tamper-proof storage. Alerts are generated from ingested local evidence on snapshot processing, not a continuously running web monitor.

The default database is ignored by Git. Custom database paths and exported reports need the user's normal data handling. The server is loopback-only, with JSON writes and cross-origin rejection; it is a single-user local tool without production authentication or schema migrations. Imports are limited to 4 MiB, 1,000 sources/entities and 5,000 claims. Pairwise conflict analysis and the original small SVG graph favor modest investigations.

The supported Graphiti episode adapter remains an optional opt-in external integration. It is type-checked but not exercised with real credentials/databases, and does not yet map returned edges into the offline engine or guarantee model-derived identity/validity.

## Best next enhancements

1. **Real extraction contracts:** reviewed source-to-claim extraction and numeric/unit normalization, with held-out labelled evaluation and exact provenance checks before model output enters an investigation.
2. **Verified connectors:** changedetection.io snapshot import and a tested Graphiti episode/edge round trip, retaining immutable source IDs and both clocks.
3. **Team-scale work:** authenticated collaborative review, database schema migrations, tamper-evident history and a scalable graph layout, once the local workflow has real users.
