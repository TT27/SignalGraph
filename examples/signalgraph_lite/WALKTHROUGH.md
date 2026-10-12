# 60-second LinkedIn walkthrough

**0–10s · Overview**
“I built SignalGraph Lite, an open-source Graphiti example for tracking changing company intelligence. This reproducible demo compares twelve fictional announcements across two periods: six entities, four changes, and two contradictions.”

**10–25s · Changes → filter Conflicts → Helios**
“Helios publishes two different revenue forecasts for the same quarter. A newer source doesn't automatically make the earlier one false. These validity windows overlap, so the engine flags a conflict and keeps both exact excerpts.”

**25–37s · Evidence drawer**
“Every detection links to document IDs, publishers, and verbatim evidence. Publication time and asserted validity are separate. I use evidence classifications rather than fabricated confidence scores.”

**37–48s · Entity explorer → Nova Labs / Nova Energy**
“Entity IDs preserve relationships and historical assertions. ‘Nova’ is a shared alias, so the system leaves that claim unverified instead of merging two companies. Explicit corrections and retractions are handled separately.”

**48–60s · Timeline → Overview / Export evidence**
“The offline demo needs no keys, LLM, or database. Twenty-five automated tests pass, with eight of eight labelled synthetic detections matched. That's a regression result, not real-world accuracy. An optional Graphiti episode adapter is included, with external integration clearly marked unverified.”

Recording preparation: start the local server, use a 1440px desktop viewport, hide unrelated tabs, and preload the fixture. Show `s02` and `s07` in the Helios drawer. Do not present synthetic fixture URIs as real announcements. Include a repository link only after you have approved pushing/publication.
