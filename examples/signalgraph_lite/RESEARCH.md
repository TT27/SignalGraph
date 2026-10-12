# Open-source research and product decisions

Researched 13 October 2026 (Australia/Sydney), using the projects' GitHub READMEs and official documentation. This is a design comparison, not a performance benchmark. No source code or third-party assets were copied into SignalGraph Desk.

| Project / primary sources | Useful pattern | Implemented in SignalGraph Desk | Boundary |
|---|---|---|---|
| [changedetection.io](https://github.com/dgtlmoon/changedetection.io), [README](https://github.com/dgtlmoon/changedetection.io/blob/master/README.md) | Focused monitoring rules, retained text snapshots and readable diffs | Entity/type watches, deduplicated local alerts and word-level statement diffs | No website fetching, polling, hosted AI, or external notification delivery |
| [OpenCTI](https://github.com/OpenCTI-Platform/opencti), [official investigation documentation](https://docs.opencti.io/5.9.X/usage/pivoting/) | Source-linked knowledge, entity relationships, and analyst investigation workflows | Evidence graph, review board, resolution rationale and retained decision history | General company/vendor intelligence; no STIX compatibility or inferred threat relationships |
| [Datasette](https://github.com/simonw/datasette), [README](https://github.com/simonw/datasette/blob/main/README.md) | Local SQLite data becomes an explorable interface and API with explicit source metadata | Persistent, isolated investigations; validated JSON imports; evidence and Markdown exports | No arbitrary SQL execution, cloud publishing or Datasette dependency |
| [Cytoscape.js](https://github.com/cytoscape/cytoscape.js), [official documentation](https://js.cytoscape.org/) | Interactive graph exploration, entity selection and data-driven styling | Keyboard-selectable SVG entity graph, source-linked edges and temporal scope | Original small SVG renderer; no Cytoscape dependency or graph-theory inference |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal facts and episode provenance | Existing supported episode adapter plus distinct observation and validity clocks in replay | External LLM/database ingestion remains explicitly unverified |

changedetection.io and Datasette advertise Apache-2.0 licenses. OpenCTI separates Apache-2.0 Community and separately licensed Enterprise editions. Cytoscape.js uses MIT. These projects are inspiration only; the original SignalGraph example remains under the fork's Apache-2.0 license. No Enterprise feature implementation or licensed assets were reused.

## Why this direction

The original fixture dashboard demonstrated detection but could not store a user's own investigations or support follow-up work. The upgraded tool closes that gap: bring structured evidence, distinguish what was known from when it applied, investigate source relationships, record a defensible decision, watch for new matching events, and hand someone a source-linked briefing.

SQLite and browser-native SVG keep startup independent of services and JavaScript build tooling. JSON is the explicit import contract because free-text extraction would introduce model dependencies and unmeasured errors. Watches evaluate local ingested evidence instead of pretending to monitor live feeds. A status such as “resolved” records an analyst decision without altering contradictory source claims.

## Chosen differentiator

**Two-clock investigation.** The observed cutoff constrains which sources can be known; the validity date constrains which assertions apply. A February publication cannot explain a January observation-time state. A known February correction can still leave the original January assertion visible at its historical validity date. The UI exposes both clocks and labels assertion states rather than claiming to determine truth.

## Deferred integrations

A future changedetection.io connector could supply real text snapshots, but still needs explicit claim extraction, provenance mapping, and deduplication. A Graphiti round trip could ingest episodes and map returned graph edges, but needs actual model/database validation and an identity/validity contract. These are future work, not current functionality. No comparative accuracy or speed claims have been made.
