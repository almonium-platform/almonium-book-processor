# Runbook

Operator procedures that exist nowhere else. Each names the page or command,
what it changes, and whether it pays a provider. Nothing here calls a provider
unless it says so.

## The local stack

- The image copies `src/` at build time. After any change under `src/` or to
  `pyproject.toml`: `docker compose up -d --build web worker`. Environment-only
  changes: `docker compose up -d web worker`. `docker compose logs -f web
  worker` when something looks stale; hard-reload the browser for static files.
- **Do not rebuild while a paid job is running.** Replacing the worker
  container kills its task; tasks are acknowledged on receipt, so the broker
  does not redeliver, and the run stays "running" (next section). The edition
  page lists queued and running jobs at the top; wait for them, or accept a
  reconciliation. The broker's own acknowledgement timeout is six hours
  (`compose.yaml`) so the broker never kills a long job itself; Celery's task
  time limit is two hours (`CELERY_TASK_TIME_LIMIT`).
- spaCy models are wheels in the image; the embedding model is downloaded on
  first use, so the first offline alignment after a fresh image takes minutes.
  After changing a model pin: `manage.py check --tag nlp`.

## A run stuck in "running"

Symptoms: a pipeline run shows running with no worker activity; a book
adaptation stops with "A chapter is still running; reconcile it before
retrying"; a fidelity audit says "already running; inspect its ledger before
retrying".

Cause: the worker was lost mid-request (rebuild, restart, out of memory, the
two-hour limit). Nothing recovers this automatically, on purpose: a paid
request must never be blindly repaid.

1. Open the run's AI calls on the edition page. If an `AIRun` has a completed
   response recorded, the provider answered and nothing was lost; if it is
   still `submitted` with no usage, the money may or may not have been spent
   and the provider's dashboard is the only witness.
2. In `/admin/` (Pipeline runs), set the run's status to `failed`. Leave the
   `AIRun` rows alone; they are the ledger.
3. Queue the same job again from the edition page. A chapter pilot whose
   previous answer was completed and still validates is reused without a new
   call; anything else makes a fresh, paid request.

## A withdrawal that never completed

A published edition is withdrawn before it is purged: the processor asks the
product API to stop serving the book and only then destroys the content. If
the API was down, the edition keeps `withdrawal_requested_at` and appears on
**Removed books** above the tombstones — the only place a stalled withdrawal is
visible. Check the backend is reachable, then repeat the removal from the
edition page; it asks the API again and purges once confirmed. Learner
progress and orders survive on the API side, and republishing the same slug
revives the book. No provider call.

## A promotion that failed

The promote run's summary line says what happened and its error why not
([PROMOTION.md](PROMOTION.md)).

- *Capabilities refused*: the bundle schema or newest catalog migration
  differs. Deploy the same build to both sides, then promote again.
- *Timeout*: the target did not answer within the client's own timeout; check
  the target's web container and retry. Landing is idempotent, so a bundle
  that half-arrived is safe to send again.
- *Slug held by a different edition on the target*: resolve on the target
  (purge or rename) before retrying.
- *Landed but nothing is public there*: "Publish there after the copy lands"
  was not ticked, or the source edition was not published first. Publish on
  the target; sources first.
- *Companion reads paragraph-only on the target*: retired artifacts do not
  travel. On the source, check the edition's "Parallel companions" table is
  current, refresh where it is stale (free), then promote again.
- Manual path when HTTP is not an option: `manage.py export_edition_bundle
  <slug> bundle.zip` on the source, `manage.py import_edition_bundle
  bundle.zip [--origin laptop] [--publish]` on the target.

## After a text correction

An approved block revision retires the edition's artifacts. What comes back
by itself (free): lexical analysis, source-text QA, and the offline sentence
alignment of every companion pair that had one. What does not:

- **Chapter analysis**: requeue it from the edition page; unchanged windows
  are reused and only the changed chapter's windows are billed.
- **Fidelity audit and difficulty verdict**: carried forward when the edit is
  a phrase inside a block or one of the audit's own suggestions. A chapter-
  scale edit leaves the audit stale; the audit panel prices the re-read.
- **Publication and promotion**: both are stale after any correction.
  Republish, then promote; check the companions table first.

## Paid jobs, where they start, what they cost

| Job | Where | Tier | Recorded cost so far |
|---|---|---|---|
| Metadata detection | edition page, on upload and on demand | Luna | a fraction of a cent per book |
| Chapter analysis | edition page | Luna | about $0.10 per 48 Ukrainian windows; resumable |
| Metadata translation | after a translation, and on demand | Luna | small, one call per chapter |
| Translation | product API order, or the edition page | Terra (Luna draft tier) | $2.06 for Frankenstein, direct mode |
| Chapter adaptation pilot | edition page | Terra | about $0.06 per chapter |
| Book adaptation | edition page | Terra | resumable in chunks of three chapters |
| Fidelity audit | edition or pilot page | Terra ("quality") or Luna ("draft", about a tenth) | $1.32 for the whole B2 |
| Floor probe | edition page | pilots + judge + audit | three chapters' worth of each |
| AI alignment review | alignment review page | Luna, Terra on escalation | $0.67 for Frankenstein EN–FR |

Every call is an `AIRun` on the run that made it; the edition page shows each
run's calls and spend, and `GET /api/v1/internal/ai-spend/` sums the ledger
for the product API. A purge keeps the ledger rows on the tombstone. Batch
mode has been off since the provider's file-access regression of 2026-08-30;
every job runs direct at full price.

## Retrying a failed edition

**Retry** on a failed edition does the right thing for its kind: reprocesses
the source file, reprocesses normalized content, resumes a book adaptation
with completed chunks reused, or re-queues a parallel translation. It refuses
an edition that is not failed.

## Commands

- `manage.py check --tag nlp` — every pinned spaCy model loads and lemmatizes.
- `manage.py check_calibration <fixtures> [--predictions file]` — validate
  difficulty fixtures and compare saved predictions, offline.
- `manage.py backfill_floor_probe <edition-slug>` — record a floor probe from
  pilots that were already judged and audited.
- `manage.py export_edition_bundle` / `import_edition_bundle` — manual
  promotion (above).
- `manage.py clear_inferred_alignment [--edition] [--delete]` — drop inferred
  alignment rows from editions aligned by construction; reports without
  `--delete`.
- `manage.py preview_sentence_alignment` — queue a paid sentence alignment
  for one public-library chapter; does not publish.
