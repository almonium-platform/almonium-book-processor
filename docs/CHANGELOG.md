# What shipped

Newest first, one entry per day the service changed, with the commits that
carry the work. Measurements recorded on the day live here too; the backlog
keeps only what is open. Cross-repository work names its repository.

## 2026-09-19

- Every text revision on a judged public edition refreshes its chapter
  analysis by itself, not only one that applies a fidelity finding: a
  phrase-sized change carries the verdict forward for free, a bigger one
  re-queues the run and the judge re-reads only the chapters that changed.
  An edition never judged, a private work or a parallel translation is left
  alone; applying findings no longer buys a book's first analysis.

## 2026-09-18

- `source_edition` now means "generated from, block for block" and is set on
  parallel editions only; an uploaded translation or abridgement names its
  work instead, and the model refuses a source on anything else. Inferred
  alignment for a standalone edition is built on demand against the work's
  canonical edition, is never re-run on ingest or after a revision, and gates
  neither review completion nor publication. The French Frankenstein, whose
  $0.667 adjudication had been orphaned by such a rebuild, was detached and
  its inferred alignment cleared. A rebuild now keeps every reviewed group,
  restored from the block ids on its review, and re-infers only the rest.
- Confirming metadata with a blank blurb or year no longer pins the field, so
  a later "Detect with AI" still fills it (`ae4a21a`).
- Other languages get adaptation prompts of their own (B2 v8, B1 v6) with the
  English-only wording removed; adapted blocks and audit corrections are gated
  by an offline language check and a wrong-language answer is not reused on
  retry (`c23951e`). Docs indexed and refreshed (`41d9cdc`).
- Fidelity findings became an apply-or-dismiss workflow: both sides of every
  finding, a word-level preview of the correction inside its clause, a
  correction replaces the clause the editor rewrote and keeps the sentence's
  punctuation, advice ("Use …") is refused as text, dismissal is undoable
  (`9bb352e`, `a407fc4`, `0e20f1f`, `e29b6b6`, `be47a4d`, `b9cf605`,
  `c65bd67`, `fc5d80a`, `170f2c8`, `6739df3`).
- Audit and difficulty verdicts carry forward when their own suggestions are
  applied or a fix changes a phrase rather than a chapter; a re-read respects
  past decisions and the panel says what carries (`dc23792`, `03bcad4`,
  `a41eed6`, `35e0279`, `e02ab10`).
- The adaptation floor is found per book, one rung at a time, recorded from
  evidence and carried in promotion bundles (decision 13; `c8b1b9e`,
  `56f783b`, `28f0d0e`, `686886e`, `c6874cf`). The published B2 was audited
  on Terra, run `f06a3841`, $1.32: 7 material, 36 minor, 2 uncertain. All
  suggestions were applied from the page; the first bulk apply pasted
  corrections over words still in the text in 14 blocks, which the re-read of
  chapters 1–5 caught and a repair rebuilt from the pre-apply text; two
  "Use …" suggestions were advice and were applied by hand; one minor finding
  (c6.p23) is left to the editor. `adapts_to = B2` is recorded with the run
  ids; incremental spend for the fixes $0.09 (`51162b2`).
- Offline sentence alignment survives corrections: the post-revision refresh
  re-queues the offline job for every companion pair that had one, in its
  orientation and model; unchanged blocks come back from cache (the B2 refresh
  embedded 42 of 815 blocks). The edition page shows a "Parallel companions"
  table per pair with alignment state and a one-click refresh (`055b2af`).
- Generated chapter and metadata prose is validated in the edition language;
  short Ukrainian and Russian are told apart by alphabet and Lingua; rejected
  assessments are retained for review, never served (`a20ca38`, `3bd8a63`,
  `40c71a5`).
- B1 was tried five ways: five prompt versions, blind controls, Terra at high
  reasoning, and a two-stage B2→B1 pass. Every result judges B2 and the
  second pass adds material drift; resumable B1 editions are kept as
  experiments, not products (`c5f01ed`, `f2307bc`, `9480a83`, `ad2521b`,
  `c40fcc8`; `docs/evidence/b1-20260918/`).
- Fidelity audit caches keyed by what changes an answer, not price or tier;
  enough output budget for a reasoning model; quotes verified without the
  quotation marks the model wraps them in (`861df11`, `9fe7231`, `43d854d`,
  `44c9dd3`).
- Local broker acknowledgement timeout raised to six hours (`2fa4a54`); the
  catalogue grouped by work and user imports as one flat table (`e276a3a`,
  `0c14605`); metadata translation retries a transient provider error
  (`a54dab9`).
- Sibling repositories: backend stores and serves `adaptsTo` (`almonium-be
  709df465`), Angular tile captions (`almonium-fe a68db79`) and mobile library
  feet (`almonium-mobile 2cf5b51`) show the levels a work has; level promises
  removed from the web landing and Premium copy (`almonium-fe b07c669`).

## 2026-09-17

- Editions move between environments as promotion bundles with a deployed
  secret, a capabilities check before anything is sent, and retired artifacts
  left out (`90c2b75`, `b69a0e2`, `85c3fa5`, `f202ab5`, `86d97a5`).
  Production follows staging on every push with a hold switch, and `main`
  points at what production runs (`846f386`, `8fde8eb`, `205d9ad`).
- B1 adaptation prompts and standalone chapter pilots (`3195004`).
- A translated edition is named and described in its own language, contents
  included, from the metadata-translation run that fills it (`af5ca63`,
  `1043a70`, `4e7ab19`, `582b0ca`); the level left titles and the Ukrainian
  Frankenstein got its own (`e3a73b7`); the chapter count travels with a
  publication (`d4852c9`).
- Chapter analysis precedes translation and travels with it; a chapter's last
  description keeps serving while its analysis is stale (`fdeee90`,
  `1f16403`).
- Drop-cap detection repaired; clause alignment with passage provenance
  (`39399bf`); machine translations keyed by their text, the API's refusal
  quoted (`c81318d`).
- Edition page: each run's AI calls and spend; the adaptation card collapsed
  and its hardcoded level dropped; the offline alignment form laid out
  (`5554c15`, `3b71de9`, `10a4239`).

## 2026-09-16

- Full-book offline sentence correspondence with staff preview and progress
  (`864b36e`); long-sentence recovery and distinct reciprocal matches
  (`5e388cf`, `docs/ALIGNMENT_FIX_20260916.md`); word-level changes and CEFR
  labels in the parallel reader (`fb216ec`, `52d2dff`, `6bef073`).
- Attested chapter vocabulary served from versioned lexical artifacts
  (`07b0402`, `docs/CHAPTER_VOCABULARY.md`); reached Angular and mobile the
  same day (`almonium-mobile 8387875`).
- Adaptation difficulty failures tracked as reassessment-cleared review
  warnings; a passing review labelled with its target (`0386d66`,
  `7ba3e0f`); publication gated on the source being released (`c716f0f`);
  review items point at the content they ask about (`3b3541a`).
- CI deploys when a supplied digest skipped the build (`485689b`).

## 2026-09-15

- Inherited edition pairs and paid sentence previews served to the product
  API, with no paid inference for exact inherited correspondences (`21c32c4`,
  `9e1a709`); reader-safe chapter metadata for published editions
  (`f803b0c`).
- Adaptations gated on current target difficulty; reviewed chapter pilots
  applied with revision history and reassessment (`79987e0`, `53abd48`).

## 2026-09-14

- Paid B2 chapter adaptation pilots with side-by-side review, prompt v4
  fidelity guards and a prompt-drift check; complete aligned B2 drafts as
  resumable chapter jobs (`c33554a`, `5ab2ba8`, `150daa7`). The full
  Frankenstein draft: 815 aligned blocks.
- Multilingual difficulty fixtures and offline calibration reports
  (`9b1fc9d`); per-chapter difficulty rows; a book's queued and running jobs
  at the top of its page (`8ecde98`, `a90923c`).

## 2026-09-13

- Resumable staff chapter analysis with audited AI attempts; chapter and book
  difficulty projected without new spend; the edition cap raised to 1,024
  windows; a paid window with sloppy citations kept with a reason
  (`29f79d7`, `66f3ae2`, `d2692f2`, `56979ec`).
- The product API orders translations and library ingests as jobs it can
  watch (`552c313`); the translation register is a column (`343de96`); a
  publication hand-off fails fast and says why (`78e5e0b`, `bcb385a`).
- Vocabulary analysis in every language spaCy has a model for (`4048624`);
  a failed attempt's cost kept on retry (`51aca70`); metadata detection on
  demand (`d992853`); page-break-only TEI divisions skipped (`247f938`).

## 2026-09-06

- Metadata detected from the file header and one small AI call, for
  catalogue uploads and private imports (`cbb51ff`, `ea00d72`, `c4e1cf7`).
- A book can leave: purge here, withdraw from Almonium, and a tombstone that
  keeps the ledger honest (`0ea10b6`, `63170dd`).
- A spaCy model is required for vocabulary analysis and the image is built
  with the pinned model wheels (`b2b8b09`, `bf3ad6d`); the AI ledger is
  summed for the product API's spend page (`8f5335a`); the cover page is
  recognised (`1f3aa09`).

## 2026-08-29 – 2026-08-30

- Versioned lexical artifacts and reviewable source-text QA with drop-cap
  detection and a correction workflow (`83297fa`, `29050c8`, `fa1b09b`,
  `deb34a5`).
- The parallel tree is rooted in the schema and built by translation, not
  inference; a staff side-by-side reader (`c4d3b0a`, `24bb474`, `c1a5f7a`).
  Frankenstein was translated into Ukrainian end to end: 30 chapters, 815/815
  blocks, 63,656 words, zero QA warnings, length ratio 0.917, no block below
  0.80 confidence, $2.06 in direct mode.
- Direct (non-Batch) execution added because the provider's Batch service
  began rejecting every input file on 2026-08-30 ("Cannot find file … or
  organization does not have access to it"), reproduced with a single-line
  batch on both endpoints while the same files upload, report `processed`
  and download fine. Batches had succeeded on 2026-08-23. Direct mode runs
  the identical requests through the Responses API, forfeiting the 50%
  discount.
- The blind model comparison (English chapter V into French): Sol, Luna and
  Terra all returned 28/28 blocks in order with correct guillemets; Sol was
  rejected for anachronistic register and a repeated adverb; Terra reads best
  and is the default, Luna the draft tier. Recorded with the calibration
  (`75ad155`).
- The Frankenstein EN–FR alignment calibration (run 2026-08-23): 815/815
  source and 807/813 target blocks aligned, 766 groups (676 1:1, 90
  two-block), mean confidence 0.825, 51 pairs below 0.65, 444 AI-accepted, 66
  human-review warnings (8.6%), $0.667. The residual is not translator
  digression: the printings divide chapters differently and the low pairs
  cluster in the letters, where salutations and signatures segment
  differently; from English chapter 10 on every chapter scores 0.80–0.87.

## 2026-08-23 – 2026-08-24

- Deterministic alignment pipeline with durable retries; the alignment review
  workspace with hierarchical AI review; manual translation for coverage gaps
  (`ecde562`, `4edc476`, `01dce2b`, `bf2dc27`, `2403653`, `d7f0e66`).

## 2026-08-01 – 2026-08-02

- The Django service replaces the conversion scripts: EPUB and TEI
  ingestion, the edition review workflow, publication to Almonium,
  owner-scoped private imports, staging deployed from `develop` (`b306b87`,
  `df38bd6`, `4e809bb`, `6730cfc`, `5788be8`, `409092b`).

## 2025-05 – 2025-06

- The original conversion scripts: HTML to text and back, chapterising,
  drop-caps. Superseded by the service; the sixteen normalised legacy
  artifacts in `build/legacy/` are their output.
