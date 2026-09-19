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
- pipeline runs and current edition artifacts;
- block and chapter alignments whose target is the edition;
- the work's `adapts_to` and the evidence behind it (bundle schema 4): the
  floor was found where the judge and audit ran, and the target keeps it
  rather than recomputing it from a ledger it does not have.

Primary keys are preserved, because artifact payloads and alignment groups
refer to blocks and chapters by id. The same edition has the same ids in every
environment.

Three things stay behind on purpose:

- **Retired artifacts.** A text revision retires the edition's artifacts and
  the refresh regenerates them, so an edited edition piles up lexical profiles
  and sentence alignments that nothing reads. They would dominate the bundle,
  so only current artifacts travel, plus any retired one a text-quality
  finding still points at. Block revisions do travel: they are small and are
  the only record that an editor overrode the source text.
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

Promotion is deployment configuration, like the product API's publisher
secret, so which environments may write to which is decided in the
infrastructure vaults and never on a page:

- `ALMONIUM_BOOKS_PROMOTION_TOKEN` is the token this environment accepts from
  a source that pushes here. An environment deployed without one accepts
  nobody.
- `ALMONIUM_BOOKS_PROMOTION_TARGETS` names where this environment may push, as
  comma-separated `name=https://host` pairs, and
  `ALMONIUM_BOOKS_PROMOTION_TOKEN_<NAME>` holds each target's token. A target
  without its token is not offered.

The tokens live in `almonium-infra` under `books.promotion_secrets` in the
shared vault, one per environment. Staging is deployed with production as a
target; production has no targets. A laptop's `.env` carries staging's token,
so a bundle reaches production only through a build that staging already
served. The promotion token is deliberately not the publisher secret: that
one guards what the product API may do on its processor, and it would
otherwise have to be copied to every machine that promotes.

## Pulling from a higher environment

Direction is configuration, not code: nothing stops production from being
given staging as a target. What the push model cannot do is reach a laptop,
which has no public host. So a laptop pulls instead, with the same token it
already pushes with:

```bash
docker compose exec web python manage.py pull_edition_bundle staging --all
docker compose exec web python manage.py pull_edition_bundle staging <slug> [<slug>...]
```

The command asks `GET /api/v1/internal/promotions/exports/` what the target
offers (every reviewed edition of a public work, each naming the edition it
was generated from) and refuses before fetching anything when the bundle
schema or catalog migration differ. `--all` fetches only the editions nothing
else was generated from, because their bundles carry the sources. Each bundle
comes from `GET /api/v1/internal/promotions/exports/<slug>/` and lands
through the same import as a push, so the same rules apply: primary keys are
kept, a local edition with the same id is overwritten, the AI ledger and
publication state stay where they were. `--publish` queues the local product
API's publication afterwards and `--save DIR` keeps the zips.

Staging never learns the laptop exists: the token guards reads the way it
guards writes, and both only ever cover public, reviewed editions.

This is also how a laptop is re-seeded after its Docker volumes are lost:
anything that reached staging comes back with `--all`; only work that was
never promoted is gone.

## Manual transfer

The same bundle can be moved by hand:

```bash
manage.py export_edition_bundle <edition-slug> bundle.zip
manage.py import_edition_bundle bundle.zip [--origin laptop] [--publish]
```

The import refuses a bundle written at a different bundle schema version or
catalog migration, exactly as the endpoint does.
