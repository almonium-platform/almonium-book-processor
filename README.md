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
