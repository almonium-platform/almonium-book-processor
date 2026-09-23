# Almonium Books

Almonium Books is the Python service for importing EPUB and TEI editions, reviewing
normalized content, running slow book-processing jobs, and publishing a stable
REST representation to Almonium clients.

It is a Django application, not a CLI product. The operator UI is at `/`, the
Django data admin is at `/admin/`, the REST API is under `/api/v1/`, and the
OpenAPI document is available at `/api/schema/`.

## Architecture

- Django and server-rendered HTML provide the staff-only admin panel.
- Django REST Framework exposes staff orchestration endpoints and read-only
  public book endpoints.
- Celery workers ingest EPUB and TEI P5 sources, run local sentence splitting
  and embedding alignment, and own every paid job: metadata detection, chapter
  difficulty analysis, translation and metadata translation, same-language
  adaptation, fidelity audits and floor probes. Requests go to the Responses
  API directly; the Batch path exists but is not the default (see the backlog).
- PostgreSQL stores normalized works, editions, chapters, blocks, runs,
  warnings, prompts, and model metadata.
- Uploaded source files are files, not database blobs. Local development uses a Docker
  volume; deployment uses an environment-specific persistent host directory.
- spaCy provides local sentence segmentation. Sentence Transformers provides
  multilingual embeddings used by the monotonic alignment candidate builder.
- AI calls sit behind a provider interface with a project-scoped
  `OPENAI_API_KEY`. The model is chosen per job in `config/settings.py`: Luna
  for the cheaper tiers (alignment's primary pass, metadata, chapter analysis,
  draft translation) and Terra for text a reader will see (quality translation,
  adaptation, fidelity audit). Every call is an `AIRun` with its prompt
  version, token usage and estimated cost.

Internal identifiers are UUIDs. Public edition slugs are the human-readable URL
identifier. Private user imports deliberately have no public slug contract and
are addressed by an opaque UUID through the owning user's Almonium session.
Numeric legacy book IDs are discarded rather than represented in the new schema.

## Local development

For a containerized stack:

```bash
cp .env.template .env
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Open <http://localhost:8000>. Local PostgreSQL and RabbitMQ are exposed on
ports `5433` and `5673`, avoiding the neighboring backend's normal ports.

### Seeing your changes in the running stack

The image copies `src/` at build time and no source directory is bind-mounted,
so an edit on your machine is **not** live in the containers. After changing
Python code, templates, static files, or dependencies, rebuild and restart the
affected services:

```bash
docker compose up -d --build web worker
```

Rules of thumb:

- Views, templates, tasks, or any code under `src/` — rebuild `web` and
  `worker` as above. Templates and static files are baked into the image and
  collected by `collectstatic` during the build, so a plain restart is not
  enough.
- Only Celery task code — `docker compose up -d --build worker` is enough, but
  rebuilding both is always safe.
- `.env` or compose environment values — no rebuild needed, just
  `docker compose up -d web worker` to recreate the containers with the new
  environment.
- `pyproject.toml` dependencies — same rebuild; the dependency layer is cached
  and only reinstalls when that file changes.
- New migrations — the `web` container runs `migrate` on start, so the rebuild
  above applies them. To apply them without a restart, use
  `docker compose exec web python manage.py migrate`.

Then hard-reload the browser (static assets are cached) and check the logs if
something looks stale:

```bash
docker compose logs -f web worker
```

For a fast Python-only test loop:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
```

Install `.[worker]` when running NLP locally; it pins one spaCy model per
supported language, and `manage.py check --tag nlp` proves each loads and
lemmatizes. The first embedding request may download the configured model; CI
installs only `.[dev]`, never downloads models and never calls paid APIs.

## Migrated catalogue

The raw legacy `/books` input was intentionally removed after normalization.
The 16 normalized artifacts remain in the ignored `build/legacy/` directory.
They are a one-time migration input, not application source.

After creating an admin user, open **Import migrated books**, select all JSON
files in `build/legacy/`, and submit them together. The importer is idempotent,
imports originals first and links translations to their source editions
regardless of file-selection order. The historical filenames and IDs do not
become database identifiers.

Only production needs the full catalogue. Staging has its own small logical
database so migrations and processing experiments cannot damage production;
keep it empty or load only representative editions. The databases share the
existing PostgreSQL server, so this isolation does not mean another database
server or a second manually maintained catalogue.

## Source and review lifecycle

An uploaded EPUB or TEI XML file is deliberately retained after it has been
normalised. It is the provenance record for the edition and allows a book to be
reprocessed with a fixed importer, a new processor version, or a later review
decision. The database stores the relative file name and SHA-256; the file
itself is stored under `MEDIA_ROOT/sources/`. In production and staging,
`../almonium-infra` mounts a persistent host directory into both the web and
worker containers. Removal is one audited operation described under *Removing
a book* below: a purge destroys the source file together with the text and
leaves a tombstone. Do not delete sources just because normalisation succeeded.

Edition state is intentionally separate from individual pipeline-run state:

```text
Draft (reserved) → Queued → Processing → Ready → Published
                                    ├── Needs review → Ready
                                    └── Failed
```

The upload form needs only the file and creates `Queued`; the worker moves it
to `Processing`. After ingestion a metadata stage reads the header, checks it
against the opening text with one small `OPENAI_METADATA_MODEL` call (a fraction
of a cent per book, recorded as an `AIRun`), fills in the description and
first-publication year, and derives the slugs; anything pinned in the form is
kept. An editor confirms the result on the edition page before publication. A
clean import, or one with informational notices only, becomes `Ready`. An actionable
importer warning becomes `Needs review`. In the custom edition page, **Complete
review** records the reviewer, timestamp, optional notes, source hash, and
warning count, then moves the edition to `Ready`; it never publishes it. A
failed parse becomes `Failed`. Publication remains a separate, deliberately
explicit workflow step.

An original edition is a complete readable state. It does not require another
language edition or alignment. After normalization, the worker independently
derives versioned lexical artifacts, including a book-level profile and up to
50 useful recurring words with frequency and source evidence. Enrichment runs
are observable but do not block a sound original from becoming available.

For any existing or newly uploaded edition, the edition page exposes **Run
lexical analysis** and **Scan source text**. New uploads queue both automatically;
existing editions can be backfilled with the same buttons. Source-QA findings
show their block and evidence. Staff can edit and apply a replacement, producing
an auditable block revision, or dismiss the finding. No scanner mutates book
text autonomously.

The importer currently emits these codes:

- `empty_block_skipped` — informational; an empty source element had no book
  text to preserve.
- `image_without_source`, `empty_spine_document`, `empty_tei_section`, and
  `unexpected_chapter_count` — review items because content or structure may
  have been omitted or interpreted incorrectly.
- An unrecognised future warning code is treated as a review item by default.

Checks such as language detection, unusually short/long chapters, and
translation confidence are planned pipeline QA checks; they are not implemented
by the current source importer. Derived-edition alignment does emit coverage and
low-confidence review items after ingestion.

Alignment is hierarchical. The worker first aligns complete chapter sequences
with local multilingual embeddings, allowing 1:1, 1:2, 2:1, and missing chapter
relationships; it then aligns blocks inside those mapped windows. It does not
assume that chapter numbers match between editions. The default local model is
`paraphrase-multilingual-MiniLM-L12-v2`. It remains configurable through
`NLP_EMBEDDING_MODEL`; larger free models such as LaBSE should be adopted only
after a corpus benchmark justifies their higher memory and latency.

Staff can start **Run autonomous AI review** from an edition's alignment review
page. The worker refreshes local candidates, submits one structured request per
chapter group through the OpenAI Batch API, records the versioned prompt, model,
validated output, token usage, estimated cost, and provider batch ID, and marks
confident groups as AI-reviewed. Luna uncertainty is automatically submitted to
Terra; only Terra uncertainty remains as a human review warning. Batch processing
has a completion window of up to 24 hours.

Publication is a separate worker stage. Selecting **Publish to Almonium** from
a ready edition queues an authenticated hand-off to the product backend; only
a successful hand-off changes the edition to `Published`. The backend is the
reader-facing contract and owns the public book UUID, progress, favourites, and
rendered reader artifact. The processor keeps the normalized edition and the
source file as its provenance/reprocessing record.

Beyond the original, the worker derives further editions and artifacts, each
a staff action on the edition page with its own review gate: a paid chapter
difficulty analysis (`docs/CHAPTER_ANALYSIS.md`), block-for-block machine
translation with a title page and chapter descriptions in the target language,
same-language CEFR adaptation with a fidelity audit and a per-book floor found
from evidence (`docs/ADAPTATION_PILOT.md`), and offline sentence alignment for
parallel reading. Finished editions move to staging and production as
promotion bundles (`docs/PROMOTION.md`), never by reprocessing.

Premium user imports take the reverse route: the Almonium backend enforces the
subscription allowance and ownership, then sends the EPUB or TEI source to this
service using the existing books shared secret. Processing is asynchronous.
Status callbacks update Almonium's owner-scoped projection and produce a ready
or failed notification; normalized text and the source remain here. Private
imports skip the staff publication/review gate and can never enter the public
published-edition endpoints.

## Removing a book

Nothing about a book is undeletable, but a takedown is two different operations
depending on who else knows about the edition.

An edition that was never published is purged here and now. The normalized
blocks, the uploaded source file, and the book text stored inside AI request and
response payloads are destroyed; a private import's owner can do the same to
their own upload through the internal API.

A published edition is withdrawn first. The processor asks the product API to
stop serving the book, and only when that succeeds does the content go: the API
reads our blocks live, so purging first would leave a live catalogue entry whose
text endpoint fails. The withdrawal keeps the API's book row, so learner
progress, favourites, and translation orders survive; publishing the same
edition slug again revives it.

Both leave an `EditionTombstone`: the slug, title, source hash, who removed it
and why. The AI token ledger keeps its rows and points at that tombstone instead
of the deleted edition, because the money was really spent and a spend report
that quietly shrinks is a broken report.

**Removed books** lists those tombstones with what each removal cost, and above
them the withdrawals the product API has not confirmed yet. A withdrawal is the
one removal that can stall — it waits on another service — so the request is
recorded on the edition when it is asked for, and a row that stays in that list
is a withdrawal that never completed.

## REST resources

- `POST /api/v1/editions/upload/` — staff EPUB or TEI XML upload; returns `202`.
- `GET /api/v1/editions/` and `/api/v1/runs/` — staff operations.
- `GET /api/v1/public/editions/` — published editions only.
- `GET /api/v1/public/editions/{slug}/blocks/` — normalized public content with
  approved contextual notes anchored to exact block offsets (`docs/CONTEXTUAL_GLOSSES.md`).
- `GET /api/v1/public/editions/{slug}/chapters/` and
  `.../chapters/{sequence}/vocabulary/` — chapter list with current difficulty
  and descriptions; attested chapter vocabulary (`docs/CHAPTER_VOCABULARY.md`).
- `GET /api/v1/public/editions/{slug}/parallel/{other_slug}/` — block pairing,
  sentence correspondence and approved notes for both sides of a parallel companion.
- `POST /api/v1/internal/translations/` and `/internal/library-ingests/` —
  service-authenticated translation orders and library ingests from the backend.
- `POST /api/v1/internal/promotions/` — receives a promotion bundle from
  another environment (`docs/PROMOTION.md`).
- `GET /api/v1/internal/ai-spend/` — the AI ledger for the backend's spend report.
- `POST /api/v1/internal/imports/` — service-authenticated private EPUB/TEI import.
- `GET /api/v1/internal/imports/{uuid}/blocks/?owner_id={uuid}` — service-authenticated,
  owner-scoped private normalized content.
- `DELETE /api/v1/internal/imports/{uuid}/?owner_id={uuid}` — the owner destroys their
  own import: text, upload, and the book's words inside AI payloads.
- `GET /healthz/` — process and database readiness.

Staff resources use Django authentication. Private import resources are not a
client API: only the Almonium backend can call them, and it must supply the owner
UUID on every read. SSH is for operations and debugging, not application access.

## Deployment

The intended hostnames are `books.almonium.com` and
`staging.books.almonium.com`. CI builds an immutable ARM64 image and delegates
deployment to `../almonium-infra`, where PostgreSQL/PgBouncer, RabbitMQ,
Traefik/Porkbun TLS, persistent media, and blue/green web and worker containers
are configured.

Both hostnames are routed. A push to `develop` deploys staging and, unless
`PROD_FOLLOWS_STAGING` is off, production behind it; `prod-pipeline.yaml` is
the manual path for re-deploying a known digest. Editions reach staging and
production as promotion bundles (`docs/PROMOTION.md`), never by reprocessing.

Infrastructure vault values must be populated before the first deployment.
Never commit `.env`, provider keys, Django secrets, or database credentials.

See [`AGENTS.md`](AGENTS.md) for cross-repository boundaries,
[`docs/README.md`](docs/README.md) for what each document is for, and
[`docs/BACKLOG.md`](docs/BACKLOG.md) for what is open.
