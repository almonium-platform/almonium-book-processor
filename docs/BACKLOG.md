# Almonium Book Processor backlog

**Last reviewed:** 2026-09-18. The [docs index](README.md) says what each
document is for; this file says what is open. Dated paragraphs that used to
sit here are folded into the sections below or into the documents they cited.

Where things stand:

- Frankenstein exists as an original (C1), a published B2 adaptation whose
  floor is recorded from evidence (`adapts_to = B2`), a Ukrainian machine
  translation with its own title page and chapter descriptions, and a French
  human translation still in review. B1 was tried five ways and is not a
  product (decision 13, [ADAPTATION_PILOT.md](ADAPTATION_PILOT.md)).
- The adaptation floor is found per book by the blind judge and the fidelity
  audit, never promised; the library shows what a book actually has.
- Reader delivery across backend, web and mobile is tracked in
  [PRODUCT_READER_DELIVERY.md](PRODUCT_READER_DELIVERY.md), parallel reading
  coverage in [PARALLEL_READING_NEXT.md](PARALLEL_READING_NEXT.md). The P0–P5
  tickets in [PIPELINE_REVIEW_AND_DELIVERY.md](PIPELINE_REVIEW_AND_DELIVERY.md#delivery-tickets)
  remain the session ids; the status note under the table says which are closed.
- Every prompt is language-parameterised and gated offline as of 2026-09-18,
  but no non-English adaptation has been judged or audited. See "Open: other
  languages".

## Current baseline

The service can ingest EPUB and TEI P5/ELTeC sources into normalized works,
editions, chapters, and blocks. It retains source provenance, runs ingestion in
Celery, records importer warnings and review decisions, supports owner-scoped
private imports, and publishes reviewed public metadata to the Almonium backend.
The sixteen normalized legacy artifacts remain available in `build/legacy/`.

A normalized original is independently readable and publishable. Translations,
adaptations, alignment, lexical data, source polishing, summaries, and quizzes
are downstream editions or non-blocking versioned artifacts, never prerequisites
for the original to be a valid book.

Staging and production each run a web process and a worker. A push to
`develop` deploys staging and production follows it (`846f386`; hold switch
`PROD_FOLLOWS_STAGING`). Editions reach both as promotion bundles from the
environment that did the work (`PROMOTION.md`); nothing is reprocessed on the
target.

## Now: the adaptation floor as data (decision 13, 2026-09-18)

Implemented 2026-09-18 in the processor; see
[the ladder, probes and audit](ADAPTATION_PILOT.md#the-floor-as-data--2026-09-18).

- [x] `adapts_to` on the work: derived from the editions that pass both gates
      (blind judge at target, fidelity audit current with no open material
      finding), stored with the run ids that justify it, recomputed whenever a
      gate changes; not a form field anywhere. Floor probes (three-chapter
      pilots, judged and audited) close the ladder below the last reached
      level and are recorded as evidence too.
- [x] The publication payload carries `adaptsTo` and `reachedLevels`, and the
      floor travels in promotion bundles (schema 4).
- [x] Backend stores and serves `adaptsTo` per book (`almonium-be 709df465`);
      Angular tile captions (`a68db79`) and mobile library feet (`2cf5b51`)
      read "Original C1 · Adapted B2" from the editions a work actually has.
      `reachedLevels` rides in the payload but is not stored yet.
- [x] Fidelity audit of the **published** B2, findings applied, `adapts_to =
      B2` recorded (2026-09-18; [CHANGELOG.md](CHANGELOG.md)). One minor
      finding (c6.p23) is left to the editor.
- [ ] Republish B2 (publication is stale after the fixes) and promote, so the
      floor reaches staging and production.
- [ ] Remove the last level promises from onboarding and plan copy across
      web and mobile (web landing/Premium done in `b07c669`; audit mobile).

## Now: operator visibility

- [x] AI spend per edition and per work (2026-09-18): a tile and an "AI
  spend" panel on the edition page (per purpose and model, then per edition
  of the work, purged editions included through their tombstones), and the
  work's total beside its name on the catalogue. Only this environment's
  ledger: promoted editions were paid for where they were processed.
- [x] Where readers are behind (2026-09-18): the edition page opens with a
  "Readers are behind" table, one row for this environment's Almonium and
  one per promotion target. Almonium reads text live from this service, so
  here only metadata can be behind; a target is behind when the edition or
  anything in its chain gained a correction or artifact after the last
  successful bundle. The catalogue shows a "Behind: …" chip per edition.

## Open: other languages (2026-09-18)

- [x] Chapter analysis, metadata and metadata translation write in the edition
  language and are rejected offline when they do not (`a20ca38`, `3bd8a63`).
- [x] Adaptation prompts for languages other than English (B2 v8, B1 v6) and a
  language gate on adapted blocks and audit corrections (`c23951e`).
- [ ] Judge and audit one non-English adaptation (the Ukrainian Frankenstein
  is the candidate) before `adapts_to` is recorded for a non-English work.
  The English verdicts do not transfer, and the localized prompts have no
  evidence yet.
- [ ] Calibration fixtures cover `en`, `de` and `uk` only, with no non-English
  reference ratings.
- [ ] Eleven registry languages have no pinned spaCy model (`bg cs et ga hu is
  lv mt sk sr tr`): analysis refuses them. Decide whether they stay selectable
  for ingestion or are hidden until a model exists.

## Now: deterministic NLP and alignment

- [x] Local spaCy sentence splitting with stable character offsets.
- [x] Multilingual Sentence Transformer embeddings.
- [x] Automatic source ingestion followed by credential-free NLP stages.
- [x] Staff upload lineage for translations, adaptations, and abridgements.
- [x] Monotonic 1:1, 1:2, and 2:1 block alignment with a length prior.
- [x] Alignment coverage and low-confidence warnings.
- [x] Prevent publication when current sentence splitting or alignment is absent.
- [x] Offline sentence alignment survives corrections and each companion pair
  shows its state on the edition page (2026-09-18, `055b2af`). Promotion
  ships only current artifacts: check that table before bundling.
- [x] Frankenstein EN–FR calibration run and its 8.6% residual diagnosed
  (2026-08-30; figures in [CHANGELOG.md](CHANGELOG.md)). The residual is
  chapter division and letter segmentation, not translator digression.
- [ ] Run and record a harder calibration on Remarque DE-EN.
- [ ] Tune confidence and coverage thresholds from those results.
- [x] Decide whether canonical groups remain paragraph-level with nested sentence
  alignment or whether sentence groups become first-class database rows. **Decided:
  neither is inferred for generated editions.** See "Parallel tree" below.

Inferred alignment is no longer on the critical path. It is retained for pairs of
independently imported texts (scans, user uploads, a licensed modern translation)
and is offered only on standalone editions.

## Decided: the parallel tree is built by translation, not inference

Measured on Frankenstein: adjudicating an existing human translation cost $0.667,
while translating the same book costs roughly $0.10 (draft tier) to $1.00 (quality
tier) at Batch prices. Generating the translation therefore costs about the same
or less, and it removes the review queue entirely because the model echoes each
stable block id and the generated edition inherits the source block's
`align_group`. Alignment becomes a join, not a pipeline stage, and a new language
is one Batch job with no alignment step.

- [x] Add `Edition.parallel_role`: `canonical` roots the tree, `parallel` is
  generated block-for-block and aligned by construction, `standalone` is readable
  on its own and never block-synchronised.
- [x] Seed `ContentBlock.align_group` on every canonical edition and copy it into
  generated editions. This is the layer-1 canonical group from the pipeline doc.
- [x] Add the Batch translation pipeline with per-chapter requests, strict
  structural validation, and length/confidence QA gates. A partially translated
  book is refused rather than materialized.
- [x] Expose `parallel_role` and `supports_parallel_reading` through the edition
  API so clients can filter for side-by-side reading.
- [x] Translate Frankenstein end to end into Ukrainian (2026-08-30: 815/815
  blocks, zero QA warnings; figures in [CHANGELOG.md](CHANGELOG.md)).
- [x] Add a direct (non-Batch) execution mode after the provider's Batch file
  access regression of 2026-08-30 (details in the changelog). Direct mode
  forfeits the 50% discount: $2.06 instead of about $1.03 per book.
- [ ] Re-test Batch once the provider resolves file access, then make it the default
  again for cost.
- [x] Fix the one-off `Тоєї` (should be `Тієї`) in the Ukrainian creation scene.
  No occurrence remains in the source environment (checked 2026-09-18); the
  correction travels with the next promotion.
- [ ] Decide the reader-facing labels with the product client, keeping reading mode
  (parallel vs standalone) separate from provenance (human vs AI, disclosed).
- [ ] Make a complete, current chapter analysis a readiness condition for offering
  a canonical edition for translation, next to sentences, lexical enrichment and
  source QA. Decided 2026-09-17; see `CHAPTER_ANALYSIS.md`, "Non-English and
  parallel editions".
- [x] Translate chapter descriptions and the title page for a parallel
  translation as the metadata-translation run (2026-09-17,
  `catalog/metadata_translation.py`); the rubric is never run on a machine
  translation. Themes, setting and content flags are not translated: no
  reader surface shows them yet.
- [x] Keep serving each chapter's latest complete description and level while
  its analysis is stale or running, with a per-chapter `stale` status
  (2026-09-17).
- [ ] Requeue chapter analysis automatically after an approved text correction on a
  public edition; only the changed chapters' windows are billed.

**Model choice (blind chapter comparison, English chapter V into French, 2026-08-30):**
all of `gpt-5.6-sol`, `gpt-5.6-luna`, and `gpt-5.6-terra` returned 28/28 blocks in
order with correct French guillemets and a 1.09-1.11 length ratio. Sol was rejected
for anachronistic register (`bougie` for a period candle) and a repeated adverb the
source did not repeat, while also emitting the most tokens. Terra reads best
(`crépitait` for "pattered") and is the default; Luna is close and stays available
as the draft tier. The whole-book difference is under a dollar, so the choice is
made on register, not price.

## Next: alignment review workflow

- [x] Side-by-side chapter review with alignment confidence highlighting.
- [x] Display unmatched source and target blocks rather than silently omitting them.
- [x] Allow an operator to merge, split, and re-pair alignment groups.
- [x] Allow inline correction of derived-edition text with an audit record.
- [x] Resolve individual QA warnings and distinguish automatic from reviewed groups.
- [ ] Add language, chapter-size, paragraph-count, and boilerplate QA gates.
- [x] Prevent review completion while actionable checks remain unresolved.

The alignment workspace supports chapter review and auditable corrections. The
remaining deterministic QA gates should be added before AI adjudication.

## Now: lexical enrichment and original-text quality

- [x] Persist generic versioned `EditionArtifact` results independently of book
  readability and publication state.
- [x] Build a deterministic lexical profile from normalized blocks with spaCy
  tokenization, model or `simplemma` fallback lemmatization, and `wordfreq` Zipf
  frequency.
- [x] Produce “50 useful words from this book” with counts, chapter dispersion,
  frequency provenance, and source occurrences.
- [ ] Calibrate the useful-word ranking on at least one English and one German
  novel; adjust recurrence and frequency bounds from real output.
- [x] Publish lexical artifacts through an explicit backend contract: the
  chapter vocabulary endpoint (`07b0402`, `CHAPTER_VOCABULARY.md`) reaches
  Angular and mobile.
- [ ] Render the useful-word SEO page server-side.
- [x] Add conservative deterministic source QA for Gutenberg boilerplate,
  malformed Unicode, repeated blocks, broken line hyphenation, and probable
  split words.
- [x] Show findings for originals and derived editions; allow staff to edit and
  apply a suggested replacement or dismiss it without changing the text.
- [ ] Add chapter-size and per-chapter language-mismatch findings. The detector
  is chosen (langid plus Lingua in `ai/output_language.py`, gating generated
  prose since 2026-09-18); front-matter and verse exceptions still need
  calibrating before it runs on source text.
- [ ] Add AI adjudication for flagged source windows only. It proposes findings;
  an operator approves every text mutation through `ContentBlockRevision`.
- [x] Mark current edition artifacts stale after an approved source revision and
  regenerate sentence, lexical, and source-QA results.
- [x] Decided 2026-09-18 (`055b2af`): a text correction keeps the inherited
  block groups, re-queues the offline sentence alignment of every companion
  pair, and never recomputes inferred embedding alignment.

## Then: AI for exceptional cases

- [x] Implement an OpenAI Batch adapter behind a provider boundary.
- [x] Validate every structured response and retry only safe transient failures.
- [ ] Add explicit local-only, issues-only, and full-audit alignment modes; use
  issues-only after full-book calibration establishes reliable thresholds.
- [x] Persist provider request IDs, model and prompt versions, token usage, cost,
  validated output, and failures in `AIRun`.
- [x] Keep paid providers out of automated tests; CI never makes paid calls.
- [x] Escalate primary-model uncertainty and leave stronger-model uncertainty as
  an explicit human review warning.

No AI credential is required for deterministic NLP or lexical analysis. Paid
alignment remains an explicit staff action and records its audit and cost data.

## Later: generated editions

- [x] Select two or three candidate models and translate one representative
  chapter blind before choosing a default. Terra is the default; see above.
- [x] Translate one book into Ukrainian with explicit register; public client disclosure remains P2-3.
- [x] Add translation length, sentence-count, truncation, and structural QA.
- [x] Pilot one CEFR adaptation and generate the complete aligned Frankenstein draft; editorial approval remains open.
- [ ] Publish a small, exceptionally reviewed shelf before scaling the catalogue.
- [ ] Add pair-specific phrase colouring only for requested reader pairs.
- [ ] Add audio for a measured premium pilot only after the reader workflow is live.

## Operator and deployment work

- [ ] Import the sixteen legacy artifacts into production only after the cheap NLP
  calibration and review gates are trusted.
- [x] Populate staging with representative editions rather than the full catalogue:
  promote reviewed editions from the edition page (`docs/PROMOTION.md`).
- [x] Production Books route: routed, and deploys follow staging (2026-09-17).
- [x] Retention as one audited operation: purge and withdrawal, with a tombstone
  and the AI ledger pointed at it (README, "Removing a book"). Covers and audio
  do not exist yet, so nothing else needs covering.
- [ ] Add model-cache warm-up or an operational first-run procedure so the first
  alignment job does not surprise an operator with a large download.
- [x] `manage.py check --tag nlp` loads every pinned spaCy model and lemmatizes
  with it; the worker image is only as good as that check.
- [ ] A provider smoke test outside CI (one cheap real call per job type) is
  still missing; unit tests remain offline.

## Decisions and user-supplied inputs

Nothing secret is needed for sentence splitting and embedding alignment. The
inputs each paid pilot needed (provider and models, languages and book,
register, spend ceiling, confidence and review policy) are recorded where they
were decided: models in the blind comparison above and in
`ALMONIUM_PIPELINE_DECISIONS.md`, spend and verdicts per run in
`ADAPTATION_PILOT.md`.

Provider secrets belong in local ignored environment files or encrypted
infrastructure vaults. They must never be committed, printed in logs, or stored
inside prompt templates.
