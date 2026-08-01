# Almonium Book Processor Agent Guide

This repository owns the Python service that ingests, normalizes, reviews, and
publishes Almonium book editions. It is a web application with background
workers, not a collection of one-off conversion scripts. EPUB and TEI P5 XML
(including ELTeC) are supported source formats. Keep presentation concerns out
of normalized book data.

## Repository ecosystem

This checkout is one part of a coordinated product workspace. Related
repositories are available beside it:

- `../almonium-be` is the Java/Kotlin Spring Boot modular monolith and the
  public product API. Read its `AGENTS.md`, `docs/PROJECT_AUDIT.md`,
  `docs/LOCAL_DEVELOPMENT.md`, and `docs/CI_CD_OVERVIEW.md` before changing API
  contracts, authentication, Firebase integration, or shared local services.
- `../almonium-fe` is the Angular web client. Treat reader, upload, job-status,
  and public API changes as cross-client work; read its `AGENTS.md` before
  editing it.
- `../almonium-mobile` is the Expo/React Native client. User-upload and reader
  APIs may affect it even when the first UI is web-only; preserve its Firebase
  bearer-token boundary.
- `../almonium-infra` owns deployed topology, Ansible, Docker Compose,
  Traefik/Porkbun TLS, PostgreSQL/PgBouncer tenants, RabbitMQ vhosts, backups,
  encrypted runtime secrets, and deployment playbooks. Read its `AGENTS.md`
  before editing it and make coordinated infra changes in a separate commit.

Do not make another repository depend on this repository's Python internals.
Cross-service integration uses an explicit HTTP or messaging contract.

## Intended service boundaries

- The web process owns the admin UI, REST resources, health endpoints, and
  orchestration commands.
- The worker process owns slow ingestion, NLP, alignment, AI translation,
  adaptation, and publication jobs. User-facing HTTP requests must not wait for
  book processing.
- PostgreSQL stores normalized metadata, blocks, workflow state, warnings,
  prompts, model runs, and review decisions. Uploaded EPUBs, illustrations,
  covers, and audio are object-storage blobs, not database rows.
- The application owns its migrations. Infrastructure provisions database and
  broker identities but does not own application tables.
- AI providers belong behind adapters. Store provider/model/prompt versions,
  validated structured outputs, token usage, cost metadata, and failures.
  Never commit provider keys or put secret values in templates.
- Offline sentence splitting and multilingual embedding alignment are book
  worker responsibilities. The separately discussed low-latency NLP HTTP
  service is not required for the initial admin application.

## Working agreement

- Preserve pre-existing and user-provided worktree changes. Resolve exact
  targets before deleting raw books, normalized artifacts, or generated media.
- Use schema migrations for persistent model changes; do not edit an applied
  migration in place.
- Keep controllers/views thin, transactions in application services, provider
  details behind adapters, and long work in idempotent background tasks.
- Every job artifact must be keyed by source hash, stage, processor version,
  model, and prompt version so retries are safe.
- Treat admin authentication and user-owned uploads as authorization
  boundaries. Authentication alone does not grant access to an upload or job.
- Add tests for behavior changes. Use fixtures or fake providers in tests; CI
  must never call paid AI APIs.
- Configuration changes are cross-repository changes when they affect
  deployment. Keep application variables, local templates, infra mappings,
  vault schemas, and encrypted values synchronized without exposing secrets.
- Stage files explicitly and commit verified changes as focused commits. Keep
  coordinated commits separate per repository and report each hash.

## Current verification

The canonical local checks are:

```bash
.venv/bin/pytest
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py check
```
