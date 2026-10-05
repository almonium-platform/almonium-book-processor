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

## The plan worker (owner's machine only)

Level adaptation can run on one of the owner's plans instead of the API: set
`ADAPTATION_GENERATOR` in `.env` to a seat such as `codex:gpt-6-astra`, then
`docker compose up -d web worker` and install the host worker once with
`./plan-service install`.

- `./plan-service install` writes a systemd user service for `./plan-worker`
  (this checkout, this shell's `PATH`, so install it from a shell where
  `claude` and `codex` run). It starts with the machine, comes back after a
  crash, and is restarted with `./plan-service restart` after a change to
  `src/`; `status` and `logs` show what it is doing. Restart it when no plan
  job is running: one cut off mid-way goes back to the queue and its run may
  need retrying from the edition page. `./plan-worker` in a terminal still
  works for a one-off; do not run both.

- Chapter pilots, floor probes and whole-book adaptations are then sent to the
  `plans` queue. The container worker never takes that queue, because the
  Claude Code and Codex CLIs are signed in on the host and not in the
  container; `./plan-worker` is a second Celery worker, on the host, that
  takes only that queue. **With the setting on and `./plan-worker` not
  running, those jobs wait in the queue**; nothing fails, nothing is paid.
- It reads the stack's `.env` and reaches the database and broker on their
  published ports (5433, 5673). It runs the code in the working tree, not the
  image: restart it (`./plan-service restart`) after changing `src/`, as you
  rebuild the containers.
- A job on a plan uses up part of the plan's weekly allowance and is recorded
  at that share of the plan's price (`ai/pricing.py`). `manage.py plan_meter`
  reads the Codex meter.
- `DIFFICULTY_JUDGES` and `FIDELITY_AUDITORS` name the pilot's blind judges
  and fidelity auditors the same way, e.g.
  `claude-code:claude-opus-5-5,codex:gpt-6.1-sol` and
  `claude-code:claude-opus-5-5,codex:gpt-6.1-sol:medium`. Each judge reads
  `DIFFICULTY_READINGS` times (three) and its middle reading counts; the
  strictest judge decides. Two auditors each read the whole pilot, and a
  material finding only one raised holds the gate only if the other confirms
  it. A plan seat in any of the three settings sends the adaptation tasks to
  the `plans` queue. Left empty, the pilot is judged and audited by the API's
  models as before. A probe records its generator, judges and auditors, so
  changing any of them makes the level probeable again.
- A Claude model is named in full, with its version: `claude-code:claude-opus-5-5`,
  never the CLI's `opus`, which follows the newest model and would change a
  judge under its own readings. Moving to a new version is a settings change,
  and makes the readings and audits of the old one out of date, as it should.
  Pages print the name the short way, `opus-5.5`.
- `./plan-manage <command>` runs `manage.py` on the host with the same
  settings, for the commands that call a plan's CLI: `plan_meter`,
  `translate_on_plan`, `review_translation`, `check_adaptation_wording`.
- **One button for a book's adaptations: a production.** On the source
  edition's page, "Produce" under Level adaptation, or
  `./plan-manage produce <source slug> --levels B2,B1 --follow`. Level by
  level, highest first, it has the source's chapters read, runs the probe,
  writes the book, has the judges read it, mends a chapter read above the
  target (its cited paragraphs once, the whole chapter once), has both
  auditors read it, writes in the corrections more than one model stands
  behind, sends the chapters those touched back to the judges and auditors
  (twice at most), and ends with the level ready or held with the reasons. A
  ready level is signed off with no person recorded (`--no-sign-off` stops at
  the verdict); it is promoted only with `--promote-to <target>`. A held
  level stops the levels below it. A failed step is started once more; a step
  nobody finishes in three hours holds the book. The page shows where it is
  and what it did. It is a run on the source edition that a short task moves
  forward every half minute, so it survives a restart of the worker.
- **Where judges are configured they are the chapter analysis.** With
  `DIFFICULTY_JUDGES` set, "Analyze" on an edition's page (and the analysis
  queued after an import, a generation or an edit) has every judge read every
  chapter, on the host worker, `DIFFICULTY_JUDGE_WORKERS` chapters at a time.
  The strictest judge decides a chapter's level and its reading supplies the
  chapter's description and recap; the single API model is not asked. An
  original is read by the whole rubric and once per judge. An adaptation is
  read for its wording alone: once per judge, and `DIFFICULTY_READINGS` times
  each only where their first readings give different levels. A chapter the judges have
  read as it stands is never read again, so asking twice costs nothing. With
  no judges configured, as on a deployed environment, the single model reads
  as before.
- **A disputed chapter does not hold an adaptation.** One substantive
  chapter in ten may read one level above the target when one judge reads it
  there and another at the target; the edition page lists such chapters. Both
  judges above the target, two levels above, or more such chapters than the
  allowance, and the gate holds as before.
- **A whole adapted edition** is held to the level its probe passed at by
  `./plan-manage check_adaptation_wording <slug>`: the pilot's judges read
  every chapter for its wording, and where they have read a chapter's current
  text their level is the one the edition's gate uses. `--revise` sends a
  substantive chapter read above the target is mended: the adapter rewrites the
  paragraphs the judges cited, and the whole chapter once if that was not
  enough. A corrected phrase keeps the judges' reading: a chapter that changed
  by two percent of its words or less carries it automatically, measured
  against the text they really read. Run the command again after larger edits,
  or after editing a chapter read above the target; the judges read only
  those.
- **Applying audit corrections.** A correction is offered for one click only
  when writing it over the quoted words cannot repeat the sentence beside it;
  otherwise the editor sees it and edits by hand. Before this guard, applying
  119 corrections in bulk left sixteen paragraphs with a repeated sentence.
  Small findings do not run out: each audit pass raises new ones, and the two
  auditors sometimes want opposite things. Settle the material ones; treat the
  rest as optional reading, not as a queue to empty.
- With `FIDELITY_AUDITORS` naming two auditors, the edition's fidelity audit
  (the page's button) is read by both, `FIDELITY_AUDIT_WORKERS` chapters at a
  time, and runs on the host worker.
- Set `CODEX_BINARY` in `.env` when an old `codex` is first on the path.
- A deployed environment leaves `ADAPTATION_GENERATOR` empty and is unchanged.

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

- **Difficulty verdict**: carried forward for free when the edit changes a
  window by a phrase (under 2% of its words). A bigger edit re-queues the
  analysis by itself, but only on an edition that has been judged before:
  unchanged windows are reused and only the changed chapter's windows are
  billed. A book never judged is not judged because of a fix.
- **Fidelity audit**: carried forward when the edit is one of the audit's
  own suggestions applied verbatim. A hand edit leaves the audit stale; the
  audit panel prices the re-read.
- **Publication and promotion**: both are stale after any correction.
  Republish, then promote; check the companions table first.

## Paid jobs, where they start, what they cost

| Job | Where | Tier | Recorded cost so far |
|---|---|---|---|
| Metadata detection | edition page, on upload and on demand | Luna | a fraction of a cent per book |
| Chapter analysis | edition page | the configured judges on the owner's machine; Luna where none are configured | Luna: about $0.10 per 48 Ukrainian windows; resumable either way |
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
