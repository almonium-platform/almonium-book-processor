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
- Celery workers ingest EPUB and TEI P5 sources and will own NLP, alignment, translation, and
  adaptation jobs.
- PostgreSQL stores normalized works, editions, chapters, blocks, runs,
  warnings, prompts, and model metadata.
- Uploaded source files are files, not database blobs. Local development uses a Docker
  volume; deployment uses an environment-specific persistent host directory.
- spaCy provides local sentence segmentation. Sentence Transformers provides
  multilingual embeddings used by the monotonic alignment candidate builder.
- AI calls sit behind a provider interface. No provider is enabled until its
  credentials and model configuration are supplied.

Internal identifiers are UUIDs. Edition slugs are the human-readable URL
identifier. Numeric legacy book IDs are discarded rather than represented in
the new schema.

## Local development

For a containerized stack:

```bash
cp .env.template .env
docker compose up --build
docker compose exec web python manage.py createsuperuser
```

Open <http://localhost:8000>. Local PostgreSQL and RabbitMQ are exposed on
ports `5433` and `5673`, avoiding the neighboring backend's normal ports.

For a fast Python-only test loop:

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
```

Install `.[worker]` when running NLP locally. The first embedding request may
download the configured model; CI unit tests never download language or
embedding models and never call paid APIs.

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
worker containers. There is no source-retention/deletion control in the
application yet, so a future deletion policy must explicitly cover the source
file, derivative media, and the audit record together. Do not delete sources
just because normalisation succeeded.

Edition state is intentionally separate from individual pipeline-run state:

```text
Draft (reserved) → Queued → Processing → Ready → Published
                                    ├── Needs review → Ready
                                    └── Failed
```

The upload form creates `Queued`; the worker moves it to `Processing`. A clean
import, or one with informational notices only, becomes `Ready`. An actionable
importer warning becomes `Needs review`. In the custom edition page, **Complete
review** records the reviewer, timestamp, optional notes, source hash, and
warning count, then moves the edition to `Ready`; it never publishes it. A
failed parse becomes `Failed`. Publication remains a separate, deliberately
explicit workflow step.

The importer currently emits these codes:

- `empty_block_skipped` — informational; an empty source element had no book
  text to preserve.
- `image_without_source`, `empty_spine_document`, `empty_tei_section`, and
  `unexpected_chapter_count` — review items because content or structure may
  have been omitted or interpreted incorrectly.
- An unrecognised future warning code is treated as a review item by default.

Checks such as language detection, unusually short/long chapters, and
translation/alignment confidence are planned pipeline QA checks; they are not
implemented by the current source importer.

Publication is a separate worker stage. Selecting **Publish to Almonium** from
a ready edition queues an authenticated hand-off to the product backend; only
a successful hand-off changes the edition to `Published`. The backend is the
reader-facing contract and owns the public book UUID, progress, favourites, and
rendered reader artifact. The processor keeps the normalized edition and the
source file as its provenance/reprocessing record.

## REST resources

- `POST /api/v1/editions/upload/` — staff EPUB or TEI XML upload; returns `202`.
- `GET /api/v1/editions/` and `/api/v1/runs/` — staff operations.
- `GET /api/v1/public/editions/` — published editions only.
- `GET /api/v1/public/editions/{slug}/blocks/` — normalized public content.
- `GET /healthz/` — process and database readiness.

The initial staff boundary is Django authentication. SSH is for operations and
debugging, not application access. Firebase authentication can be added when
user-owned uploads are exposed; ownership checks must accompany it.

## Deployment

The intended hostnames are `books.almonium.com` and
`staging.books.almonium.com`. CI builds an immutable ARM64 image and delegates
deployment to `../almonium-infra`, where PostgreSQL/PgBouncer, RabbitMQ,
Traefik/Porkbun TLS, persistent media, and blue/green web and worker containers
are configured.

Porkbun DNS still needs records for both hostnames pointing at the existing
Oracle host. Traefik's Porkbun DNS challenge obtains certificates; it does not
create the public address records.

Infrastructure vault values must be populated before the first deployment.
Never commit `.env`, provider keys, Django secrets, or database credentials.

See [`AGENTS.md`](AGENTS.md) for cross-repository boundaries and
[`docs/ALMONIUM_EBOOK_PIPELINE.md`](docs/ALMONIUM_EBOOK_PIPELINE.md) for the
longer processing roadmap.
