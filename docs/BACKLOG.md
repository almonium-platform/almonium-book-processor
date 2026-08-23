# Almonium Book Processor backlog

**Last reviewed:** 2026-08-23

This backlog records the gap between the executable service and the longer
pipeline roadmap. The order is deliberate: make deterministic local processing
observable and reviewable before adding paid AI stages.

## Current baseline

The service can ingest EPUB and TEI P5/ELTeC sources into normalized works,
editions, chapters, and blocks. It retains source provenance, runs ingestion in
Celery, records importer warnings and review decisions, supports owner-scoped
private imports, and publishes reviewed public metadata to the Almonium backend.
The sixteen normalized legacy artifacts remain available in `build/legacy/`.

Staging is deployed with a web process and worker. Production routing has not
yet been activated. The public staging catalogue is empty until editions are
reviewed and deliberately published.

## Now: deterministic NLP and alignment

- [x] Local spaCy sentence splitting with stable character offsets.
- [x] Multilingual Sentence Transformer embeddings.
- [x] Automatic source ingestion followed by credential-free NLP stages.
- [x] Staff upload lineage for translations, adaptations, and abridgements.
- [x] Monotonic 1:1, 1:2, and 2:1 block alignment with a length prior.
- [x] Alignment coverage and low-confidence warnings.
- [x] Prevent publication when current sentence splitting or alignment is absent.
- [ ] Run and record a real calibration on Frankenstein EN-FR.
- [ ] Run and record a harder calibration on Remarque DE-EN.
- [ ] Tune confidence and coverage thresholds from those results.
- [ ] Decide whether canonical groups remain paragraph-level with nested sentence
  alignment or whether sentence groups become first-class database rows.

The first production-scale run should happen without AI. It establishes how
much content the deterministic path handles and gives an honest size for the
paid adjudication queue.

## Next: alignment review workflow

- [ ] Side-by-side chapter review with alignment confidence highlighting.
- [ ] Display unmatched source and target blocks rather than silently omitting them.
- [ ] Allow an operator to merge, split, and re-pair alignment groups.
- [ ] Allow inline correction of derived-edition text with an audit record.
- [ ] Resolve individual QA warnings and distinguish automatic from reviewed groups.
- [ ] Add language, chapter-size, paragraph-count, and boilerplate QA gates.
- [ ] Prevent review completion while required error-severity checks remain unresolved.

The existing edition page, Django data admin, warning inbox, and review decision
record are foundations, not the completed alignment-review UI.

## Then: AI for exceptional cases

- [ ] Implement an OpenAI adapter behind `AIProvider`.
- [ ] Validate every structured response and retry only safe transient failures.
- [ ] Send only low-confidence alignment windows for AI adjudication.
- [ ] Persist provider request IDs, model and prompt versions, token usage, cost,
  validated output, and failures in `AIRun`.
- [ ] Keep a fake provider for all automated tests; CI must never make paid calls.
- [ ] Require human review when AI adjudication remains uncertain.

No AI credential is required for the deterministic NLP milestone. Deployment
already has a place to inject `OPENAI_API_KEY`, but application code must not
use it until the adapter, validation, audit trail, budget controls, and a named
pilot are ready.

## Later: generated editions

- [ ] Select two or three candidate models and translate one representative
  chapter blind before choosing a default.
- [ ] Translate one book into Ukrainian with explicit register and disclosure.
- [ ] Add translation length, sentence-count, truncation, and structural QA.
- [ ] Pilot one CEFR adaptation after translation quality is accepted.
- [ ] Publish a small, exceptionally reviewed shelf before scaling the catalogue.
- [ ] Add pair-specific phrase colouring only for requested reader pairs.
- [ ] Add audio for a measured premium pilot only after the reader workflow is live.

## Operator and deployment work

- [ ] Import the sixteen legacy artifacts into production only after the cheap NLP
  calibration and review gates are trusted.
- [ ] Populate staging with representative editions rather than the full catalogue.
- [ ] Activate and verify the production Books route and its Porkbun certificate.
- [ ] Define source and derivative-media retention/deletion as one audited operation.
- [ ] Add model-cache warm-up or an operational first-run procedure so the first
  alignment job does not surprise an operator with a large download.
- [ ] Add a real-model smoke test outside CI; unit tests should remain offline.

## Decisions and user-supplied inputs

Nothing secret is needed for sentence splitting and embedding alignment. Before
the first paid AI pilot, decide and record:

- provider and candidate models;
- source and target language, book, and chapter;
- target literary register;
- maximum pilot spend;
- acceptable automatic-confidence threshold and human-review policy.

Provider secrets belong in local ignored environment files or encrypted
infrastructure vaults. They must never be committed, printed in logs, or stored
inside prompt templates.
