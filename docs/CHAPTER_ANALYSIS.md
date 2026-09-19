# Chapter analysis and projections (P1-1 / P1-2)

From a public edition's staff page, use **Analyze / resume** under Enrichment.
This queues paid AI work; HTTP does not wait for a provider. No analysis is
automatically triggered by upload or by visiting the page. Private imports are
rejected at the service boundary, including calls from staff, until their
entitlement and budget policy is implemented.

The worker assesses reading demand, archaism and modernization usefulness,
source evidence, vocabulary candidates, themes, characters, setting and content
flags. It keeps a spoiler-free description separate from a recap. The staff page
shows book/chapter estimates, coverage and window evidence, with recaps collapsed behind a spoiler
label. CEFR and archaism are estimates, not certified levels or measured token
percentages. Existing editorial CEFR, book text and publication status are
unchanged even when this enrichment fails.

## Scope and limits

- Whole chapters that fit are analyzed in one request. Longer chapters split at
  block boundaries into nonoverlapping windows. Every nonblank text block is
  included once; images without text and empty chapters require no request.
- Each window has at most 24,000 UTF-8 bytes of serialized blocks. Request input
  including chapter metadata is capped at 32,000 bytes, output at 4,096 tokens,
  and the edition at 1,024 windows (roughly 24 MB of text; a 2.3 MB novel such as
  *Bleak House* needs about 130). These are request bounds, not a dollar quota.
- A single oversized block or oversized edition fails before any request is
  queued. Review segmentation or revise the limits with a processor version
  change; text is never silently truncated.
- Window assessments of long chapters feed separate chapter difficulty and
  summary artifacts. Incomplete chapters show partial estimates and remain
  excluded from the book percentile until all their windows have succeeded.
- Every quote and hard word must occur in the block it cites. Exact matches are
  required first; a stray or missing space or a case slip is repaired to the
  exact source substring and the span recorded. Citations the text cannot back
  are dropped and listed in the attempt's `validation_notes` rather than
  discarding a paid window; a window is rejected only when no evidence remains.
  Content flags with no `content` evidence are moved out of `content_flags` into
  the notes as unsupported suggestions. Rejections store our own reason with the
  chapter and window; schema and provider failures stay type-only because their
  messages may quote book text.
- First-encounter words and lexical measurements are not guessed by this prompt.
  They remain corpus-derived follow-up work. P1-3 evaluates the rubric with real
  EN/DE/UK samples; automated tests use fake responses and do not validate model
  quality.

## Chapter and book projections

`EditionArtifact.chapter` scopes an artifact to a chapter; a null chapter still
means an edition-level artifact. Each analyzed chapter has independently
versioned `difficulty` and `chapter_summary` artifacts. Its computed level,
archaism, confidence range, coverage and source evidence live in the difficulty
payload rather than a second mutable copy on Chapter. Historical artifacts
remain available; source/model/projection fingerprints identify current results.

Projection versions are independent: `chapter-difficulty-v1`,
`chapter-summary-v1`, and `book-difficulty-v1`. Upgrading summary assembly does
not regenerate difficulty artifacts or require another model request.

The initial aggregation rules are explicitly provisional heuristics:

- A chapter's level is the nearest-rank 75th percentile of its available window
  levels, weighted by non-whitespace token counts. Partial window coverage is
  retained and labelled. Archaism is the similarly weighted average rubric
  rating, not a percentage of archaic words.
- The book estimate is the unweighted nearest-rank 75th percentile of **complete
  substantive chapters**. It stores min/max, the full six-band distribution,
  complete/total chapters and analyzed/total whitespace-token counts. If some
  chapters remain incomplete, the displayed book estimate is provisional. With
  no eligible complete chapters there is no computed level.
- A whitespace-token-weighted book comparison exposes sensitivity to chapter
  sizes. These simple counts are not spaCy tokens, provider tokens, vocabulary
  measurements or CEFR classifications; they are especially weak length proxies
  for writing systems without spaces. P1-3 must evaluate the heuristics before
  treating them as calibrated reader-facing labels.
- Confidence is a min/max range of contributing model judgments; there is no
  average presented as book accuracy.
- Summaries retain ordered window sections, with spoiler-free descriptions
  separate from recaps. There is no extra AI merge call and no claim that a
  concatenated multi-window recap is a newly edited chapter summary.

Chapters default to **Substantive chapter**. Staff can explicitly label front or
back matter in each chapter's assessment or Django admin. There is no guessed
exclusion based on chapter size or title. These roles affect only book
aggregation, not the paid analysis hash. Empty chapters do not contribute.
After changing roles, use **Refresh saved assessments (no AI calls)** to update
the book projection. This action also backfills artifacts for P1-1 runs and
works without an API key. Completed analysis can be refreshed repeatedly
without duplicating artifacts or spend.

The worker projects after each successful window, so a later failed request
leaves partial results and explicit coverage. The staff UI distinguishes pending,
queued/running, partial, complete, stale, failed and no-substantive-chapters
states. Source edits and language changes invalidate artifacts; rendering also
checks current content, model and chapter-role fingerprints. A late old-model
completion may add historical results but cannot replace current projections.
Editorial `Edition.cefr_level` remains separate and is never automatically
prefilled, cleared or overwritten by the projections. Product API publication
of these artifacts is separate contract work (P0-2).

## Configuration and audit

The stage reuses `OPENAI_API_KEY` and `OPENAI_TRANSLATION_DRAFT_MODEL`, which are
already deployed settings. It takes a separate immutable snapshot of the draft
model, the existing estimated draft price schedule, rubric/prompt, schema,
processor version and request bounds. No new deployment variable is required.
If substituting a different model, review the draft price schedule too; costs
are estimates from the recorded schedule, not provider invoices.

Snapshots create dedicated `ModelConfiguration` rows and a versioned
`PromptTemplate`. Disabling these records stops future execution. Editing their
contents in place is refused; change prompt/processor version for a new
contract. Queued requests retain their original model configuration.

`PipelineRun.Stage.CHAPTER_ANALYSIS` records edition coverage, progress, errors
and references to successful window results. `AIRun` holds each individual
provider attempt, its request metadata/text, validated output, provider request
ID, tokens, estimated cost and failure state. Usage is persisted before parsing
so invalid or incomplete responses do not disappear from spend reporting. A
transport failure without usage leaves cost unknown (`NULL`), not falsely zero.
No raw provider error or validation input is copied into the public error text.

Evidence and hard-word surface strings must occur in their cited blocks.
Validated half-open offsets use Unicode code points. A repeated identical quote
currently points at its first occurrence within that block. Content flags require
content evidence but remain proposals requiring editorial judgment.

## Retries, concurrency and revisions

Use the same button to retry a failure. Successful windows with exactly matching
chapter content, source hash, language, chapter identity/title/sequence and
analysis configuration are reused, including across runs where another chapter
changed. Failed attempts remain separate ledger rows. There are no automatic
SDK retries of paid calls; explicit retries may incur additional spend.

A ten-minute renewable worker lease prevents simultaneous deliveries from
starting the same run. Busy Celery deliveries retry after 30 seconds, up to 25
times. After a worker crash, a later delivery or staff retry can reclaim an
expired lease; interrupted attempts remain recorded with potentially unknown
usage. This cannot guarantee exactly-once provider billing after a process or
network failure, but avoids presenting an unknown attempt as free.

Input snapshots are checked before requests and before accepting results.
Changed text or chapter metadata cancels the old run; queue a new snapshot.
The staff page rechecks current hashes and hides stale proposals. The public
chapters endpoint does the opposite: a chapter whose current projection is
missing or incomplete keeps serving its latest complete description and level
from any earlier run, because a stale description is better for a reader than
none. Its `analysisStatus` is `complete` when the chapter's own text hash still
matches and `stale` when that chapter's text changed since. A text correction
therefore never blanks the book page. On an edition that has been judged, a
correction refreshes the analysis by itself: a phrase-sized change carries
the verdict forward for free, a bigger one re-queues the run and re-bills
only the windows of the chapters that changed. Text already
returned by a provider after deletion is discarded; its usage is retained on
the tombstone ledger without restoring request/response payloads. A broker
dispatch failure leaves a visible failed run that the same button can requeue.

## Non-English and parallel editions

Decided 2026-09-17, after a chapter-analysis run on the Ukrainian machine
translation of *Frankenstein* was cancelled at 17 of about 50 windows
(input 69k tokens, output 21k, $0.036):

- The model reads Ukrainian competently. Every window returned a coherent
  spoiler-free description, exact hard-word surface strings from the cited
  blocks with sensible glosses, and evidence quotes present in the text. Levels
  were C1 for most windows and B2 for four, with confidence 0.93 to 0.98.
- The prompt is not designed for non-English input. It says "write
  explanations and summaries in English"; one window (Letter II) came back
  entirely in Ukrainian, including content flags and hard-word glosses, and
  nothing in the schema enforces the language. A single run would have mixed
  two languages of metadata on one edition.
- The metadata is in the wrong language for the reader regardless: an English
  description of a Ukrainian chapter helps nobody on the Ukrainian edition.
- CEFR for the translated text is not what the learner reads for. A parallel
  translation supports reading of the canonical edition, so the reading demand
  that matters is the source's. The archaism score did carry one useful
  signal: the translation chose a period register (`вельми`, `аби`, `на
  смертному одрі`) and scored 0.5 on almost every window, which is a fact
  about the translation's style, not about the original.

Therefore chapter analysis is a **canonical-edition stage that precedes
translation**, and translation jobs carry its reader-facing output across:

1. Chapter analysis must be complete and current on the canonical edition
   before it is offered for translation. It becomes part of the canonical's
   publication readiness, alongside sentences, lexical enrichment and source
   QA, rather than an optional staff button pressed afterwards. A translation
   order is settled in the product backend by a paying user, so the check
   belongs where the offer is made, not on the order.
2. The translation job translates each chapter's `spoiler_free_description`
   (and the other reader-facing summary fields worth localising: themes,
   setting, content flags) into the target language in the same job, keyed
   like the text by the source chapter hash and the summary's
   `analysis_spec_hash`. No second analysis run is made for a parallel edition,
   and the rubric is never applied to machine-translated text.
3. The public chapters endpoint serves a parallel edition its translated
   descriptions and the **source edition's** `cefrEstimate` and
   `analysisStatus`. If the canonical analysis is stale or missing, the parallel
   edition is stale or missing too; it never shows a level of its own.
4. Standalone non-English editions (a human translation read on its own, or a
   non-English original) are a separate case and may run analysis on their own
   text, but only once the output language is an explicit per-run parameter in
   the prompt and the spec hash. Until then the button is English-only.

Point 4 is implemented (a20ca38 on 2026-09-18): an edition in any language
but English is analysed with `LOCALIZED_SYSTEM_PROMPT`, v4 of the same prompt,
which writes every generated field in the input language code, and
`validate_analysis_language` rejects an answer that does not validate as that
language before it is recorded. The same-language adaptation prompts followed
on 2026-09-18; see `ADAPTATION_PILOT.md`, "Other languages".

Points 2 and 3 are implemented (2026-09-17) as a run of their own rather than
inside the translation job: `catalog/metadata_translation.py` names a parallel
translation (title, author and blurb, from the source's) and translates the
source's current chapter descriptions, one small direct call per chapter, each
keyed by what it translates and reused on retry. It is queued when a
translation completes and again when the source's analysis completes, and staff
can queue it from the edition page. The public chapters endpoint serves a
parallel translation the source's level and status with these descriptions,
and says "pending" rather than showing the source language while a
description is untranslated. Publication of a parallel translation requires
its title page to be current. Point 1, the readiness condition, is still open.

Open follow-ups: point 1 above, the readiness condition for translation. A
text correction on a judged public edition has refreshed its analysis by
itself since 2026-09-19 (see "Retries, concurrency and revisions").

## Verification

`tests/catalog/test_chapter_analysis.py` exercises full/partial coverage,
bounded windows, source evidence validation, retry cost retention, model and
metadata changes, concurrent redelivery, stale input, deletion during a request,
staff authorization, private-import exclusion, percentile aggregation, front/back
matter exclusion, partial chapter coverage, independent projection versions,
free backfill and broker failures. No paid
provider is contacted by these tests.
