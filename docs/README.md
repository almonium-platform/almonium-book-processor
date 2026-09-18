# Documentation index

Read [`AGENTS.md`](../AGENTS.md) first. The documents here are of three
kinds: how the service behaves today, decisions with the evidence behind them,
and dated records that can be reproduced from the run ids they cite. A dated
record is not updated when later work supersedes it; the backlog says so.

## Current behaviour

- [BACKLOG.md](BACKLOG.md) — where things stand and what is open. Reviewed 2026-09-18.
- [CHANGELOG.md](CHANGELOG.md) — what shipped, by day, with commits and the measurements recorded that day.
- [RUNBOOK.md](RUNBOOK.md) — operator procedures: stuck runs, stalled withdrawals, failed promotions, what a correction invalidates, what each paid job costs.
- [LANGUAGES.md](LANGUAGES.md) — one table of what each registry language has: spaCy model, wordfreq, simplemma, fixtures, prompts, books.
- [CHAPTER_ANALYSIS.md](CHAPTER_ANALYSIS.md) — the paid difficulty judge: scope, windows, projections, retries, non-English editions.
- [CHAPTER_VOCABULARY.md](CHAPTER_VOCABULARY.md) — the public per-chapter vocabulary endpoint and its provenance rules.
- [PROMOTION.md](PROMOTION.md) — moving finished editions between environments as bundles, never by reprocessing.
- [CALIBRATION_FIXTURES.md](CALIBRATION_FIXTURES.md) — offline difficulty fixtures and comparison, and what P1-3 still lacks.

## Decisions and experiments

- [ALMONIUM_PIPELINE_DECISIONS.md](ALMONIUM_PIPELINE_DECISIONS.md) — the decision record: edition tree, chapter as the unit, CEFR method, language capability, private imports, the adaptation floor (13).
- [ADAPTATION_PILOT.md](ADAPTATION_PILOT.md) — every adaptation experiment with costs, verdicts and run ids; the floor ladder; other languages.
- [PIPELINE_REVIEW_AND_DELIVERY.md](PIPELINE_REVIEW_AND_DELIVERY.md) — the 2026-09-15 review and its P0–P5 tickets, with a status note under the table.
- [ALMONIUM_EBOOK_PIPELINE.md](ALMONIUM_EBOOK_PIPELINE.md) — the original 2026-07-28 design. Historical; its banner says what changed.

## Product delivery and dated evidence

- [PRODUCT_READER_DELIVERY.md](PRODUCT_READER_DELIVERY.md) — processor → backend → web → mobile slices, as of 2026-09-16.
- [PARALLEL_READING_NEXT.md](PARALLEL_READING_NEXT.md) — parallel reading coverage assessment, 2026-09-18.
- [FRANKENSTEIN_TEXT_AND_CLAUSES.md](FRANKENSTEIN_TEXT_AND_CLAUSES.md) — legacy text defects, clause alignment and passage provenance.
- [ALIGNMENT_FIX_20260916.md](ALIGNMENT_FIX_20260916.md) — the Ukrainian–English sentence alignment fix and its real-model verification.
- `evidence/` — JSON, screenshots and run ids behind the claims above: `b1-20260918`, `parallel-20260918`, `reader-20260916`, `ukrainian-20260918`, and the superseded afternoon checkpoint `morning-brief-20260918.md`.

Sibling repositories document their own side of each contract:
`../almonium-be/docs/PROCESSOR_READER_CONTRACT.md`, `../almonium-fe/docs/PROCESSOR_READER.md`,
and `../almonium-infra` for deployment.
