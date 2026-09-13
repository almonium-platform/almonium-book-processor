# Chapter analysis: first implementation (P1-1)

From a public edition's staff page, use **Analyze / resume** under Enrichment.
This queues paid AI work; HTTP does not wait for a provider. No analysis is
automatically triggered by upload or by visiting the page. Private imports are
rejected at the service boundary, including calls from staff, until their
entitlement and budget policy is implemented.

The worker assesses reading demand, archaism and modernization usefulness,
source evidence, vocabulary candidates, themes, characters, setting and content
flags. It keeps a spoiler-free description separate from a recap. The staff page
shows window estimates and evidence, with recaps collapsed behind a spoiler
label. CEFR and archaism are estimates, not certified levels or measured token
percentages. Existing editorial CEFR, book text and publication status are
unchanged even when this enrichment fails.

## Scope and limits

- Whole chapters that fit are analyzed in one request. Longer chapters split at
  block boundaries into nonoverlapping windows. Every nonblank text block is
  included once; images without text and empty chapters require no request.
- Each window has at most 24,000 UTF-8 bytes of serialized blocks. Request input
  including chapter metadata is capped at 32,000 bytes, output at 4,096 tokens,
  and the edition at 128 windows. These are request bounds, not a dollar quota.
- A single oversized block or oversized edition fails before any request is
  queued. Review segmentation or revise the limits with a processor version
  change; text is never silently truncated.
- Window assessments of long chapters are explicitly partial. Combining them
  into chapter estimates, separate difficulty/summary artifacts, book-level
  percentiles and chapter projections is **P1-2**, not implemented here.
- First-encounter words and lexical measurements are not guessed by this prompt.
  They remain corpus-derived follow-up work. P1-3 evaluates the rubric with real
  EN/DE/UK samples; automated tests use fake responses and do not validate model
  quality.

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
The staff page rechecks current hashes and hides stale proposals. Text already
returned by a provider after deletion is discarded; its usage is retained on
the tombstone ledger without restoring request/response payloads. A broker
dispatch failure leaves a visible failed run that the same button can requeue.

## Verification

`tests/catalog/test_chapter_analysis.py` exercises full/partial coverage,
bounded windows, source evidence validation, retry cost retention, model and
metadata changes, concurrent redelivery, stale input, deletion during a request,
staff authorization, private-import exclusion and broker failures. No paid
provider is contacted by these tests.
