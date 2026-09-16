# Promoting editions between environments

Each environment (a laptop, staging, production) runs its own book processor
with its own database and media directory, and each product API reads book
text live from its own processor. A book that was ingested, aligned, analysed
and reviewed locally therefore does not exist on staging until its data is
carried there. Promotion carries it as data: nothing is recomputed on the
target, so no model call is paid twice.

## What travels

A promotion bundle is a zip holding `manifest.json` and any uploaded source
files. The manifest carries the edition, every edition it was generated from
(sources first), their works, and each edition's rows:

- chapters and content blocks, with their primary keys;
- block revisions, text-quality findings, warnings, review decisions and
  alignment-group reviews, with the reviewer recorded by username;
- pipeline runs and edition artifacts (current and historical);
- block and chapter alignments whose target is the edition.

Primary keys are preserved, because artifact payloads and alignment groups
refer to blocks and chapters by id. The same edition has the same ids in every
environment.

Two things stay behind on purpose:

- **The AI run ledger.** It records what this environment paid, and each
  product API sums its own processor's ledger for its spend report. A copied
  ledger would count the same money twice. A promoted edition shows no AI
  calls on the target; the `promoted_from` field says where the work was done.
- **Publication state.** Publish and promote runs describe what an environment
  did with its own product API, not the edition, so they never travel. The
  target's own publication is a separate step.

Private imports never travel.

## How a promotion runs

1. On the source, the edition page's **Promote to another environment** card
   lists the configured targets. It appears once an edition is ready or
   published. Submitting it records a `promote` pipeline run and queues the
   worker task.
2. The worker builds the bundle, asks the target's
   `GET /api/v1/internal/promotions/capabilities/` what it runs, and refuses
   when the bundle schema version or the newest applied catalog migration
   differ. A target on an older build therefore rejects a newer bundle before
   anything is sent.
3. The worker posts the bundle to `POST /api/v1/internal/promotions/`. The
   target lands the whole bundle in one transaction and answers which editions
   it wrote and which were already current.
4. With **Publish there after the copy lands** ticked, the target queues its
   own publication of the carried editions, sources first, skipping any that
   are already live there.

The run's summary line on the source page says what happened, and its error
says why not.

## Landing on the target

Import is keyed by primary key and is idempotent:

- An edition whose stored `promotion_fingerprint` matches the bundle section is
  skipped.
- Otherwise the edition is written in place. Its status becomes `ready`, or
  stays `published` if it is already live on the target, and the target's own
  `published_book_id`, publish runs and promote runs survive.
- Rows the target has that the bundle does not are deleted; rows in both are
  updated; timestamps are carried from the source.
- A slug held by a *different* edition on the target refuses the whole bundle.
- Reviewer and editor references are resolved by username on the target and
  become empty when no such account exists.

Alignments incoming from other editions on the target survive as long as the
blocks they point at survive; a re-ingested edition with new block ids drops
them, and the dependent edition has to be promoted again.

## Configuration

Authentication is an API token issued by a staff account on the **target**:

1. On the target's admin site, open **Auth Token › Tokens**, add a token for a
   staff user, and copy the key.
2. On the source's admin site, open **Promotion targets** and add the target's
   name, origin (for example `https://staging.books.almonium.com`) and that
   token.

No deployment configuration or vault change is needed. Configure production as
a target on staging only, so a bundle reaches production through a build that
staging already served.

## Manual transfer

The same bundle can be moved by hand:

```bash
manage.py export_edition_bundle <edition-slug> bundle.zip
manage.py import_edition_bundle bundle.zip [--origin laptop] [--publish]
```

The import refuses a bundle written at a different bundle schema version or
catalog migration, exactly as the endpoint does.
