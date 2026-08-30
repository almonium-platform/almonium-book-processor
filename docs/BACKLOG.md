# Almonium Book Processor backlog

**Last reviewed:** 2026-08-30

This backlog records the gap between the executable service and the longer
pipeline roadmap. The order is deliberate: make deterministic local processing
observable and reviewable before adding paid AI stages.

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
- [x] Run and record a real calibration on Frankenstein EN-FR. **Result (2026-08-23
  run, recorded 2026-08-30):** 815/815 source blocks and 807/813 target blocks
  aligned, 766 groups (676 1:1, 90 two-block), mean confidence 0.825, 51 pairs
  below 0.65, 444 groups AI-accepted, 66 human-review warnings (8.6%), total AI
  cost $0.667. Chapter mapping was correct throughout, including the 2:1 merge of
  English chapters 7-8 onto French chapter 7 and the 1:2 split at chapter 30.
- [x] Diagnose the residual 8.6%. It is **not** translator digression. The two
  printings divide chapters differently (24 numbered English chapters against 23
  plus `SUITE, PAR WALTON`), and the low-confidence pairs cluster in the letters
  and opening chapters where block segmentation of salutations and signatures
  differs. From English chapter 10 onward every chapter scores 0.80-0.87.
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
- [x] Translate Frankenstein end to end and review the finished edition. Done into
  Ukrainian on 2026-08-30: 30 chapters, 815/815 blocks, 63,656 words, status `ready`
  with zero QA warnings, whole-book length ratio 0.917, no empty blocks, no block-type
  mismatches, no sentence-count changes, and no block below 0.80 confidence. All 815
  blocks pair with the English canonical through a plain `align_group` join.
- [x] Add a direct (non-Batch) execution mode. The provider's Batch service began
  rejecting every input file on 2026-08-30 with "Cannot find file ... or organization
  does not have access to it" — reproduced with a single-line batch on both
  `/v1/responses` and `/v1/chat/completions`, with files that upload cleanly, report
  `processed`, and download fine with the same key. Batches succeeded on 2026-08-23,
  so this is an account or platform regression, not a payload problem. Direct mode
  runs the identical requests through the Responses API with the same validation and
  QA gates, forfeiting the 50% Batch discount: $2.06 instead of ~$1.03 per book.
- [ ] Re-test Batch once the provider resolves file access, then make it the default
  again for cost.
- [ ] Fix the one-off `Тоєї` (should be `Тієї`) in the Ukrainian creation scene
  through the block-revision workflow; 44 other occurrences use the correct form.
- [ ] Decide the reader-facing labels with the product client, keeping reading mode
  (parallel vs standalone) separate from provenance (human vs AI, disclosed).

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
- [ ] Publish lexical artifacts through an explicit backend contract and render
  the useful-word SEO page server-side.
- [x] Add conservative deterministic source QA for Gutenberg boilerplate,
  malformed Unicode, repeated blocks, broken line hyphenation, and probable
  split words.
- [x] Show findings for originals and derived editions; allow staff to edit and
  apply a suggested replacement or dismiss it without changing the text.
- [ ] Add chapter-size and per-chapter language-mismatch findings after choosing
  a reliable offline detector and calibrating front-matter exceptions.
- [ ] Add AI adjudication for flagged source windows only. It proposes findings;
  an operator approves every text mutation through `ContentBlockRevision`.
- [x] Mark current edition artifacts stale after an approved source revision and
  regenerate sentence, lexical, and source-QA results.
- [ ] Define whether a text-only correction should recompute embedding alignment
  or retain reviewed stable-block correspondence with refreshed provenance.

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
