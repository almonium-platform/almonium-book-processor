# syntax=docker/dockerfile:1.7

ARG DEPENDENCIES_IMAGE=dependencies

FROM python:3.12-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --create-home app

COPY pyproject.toml ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -c 'import subprocess, sys, tomllib; project = tomllib.load(open("pyproject.toml", "rb"))["project"]; subprocess.check_call([sys.executable, "-m", "pip", "install", *project["dependencies"], *project["optional-dependencies"]["worker"]])'

FROM ${DEPENDENCIES_IMAGE} AS runtime

ENV PYTHONPATH=/app/src

WORKDIR /app

COPY README.md ./
COPY src ./src
COPY manage.py ./

RUN --mount=type=cache,target=/root/.cache/pip \
    python -m pip install --no-deps . && \
    DEBUG=false \
    SECRET_KEY=build-only-secret-key-not-used-at-runtime \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput && \
    mkdir -p /app/media && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "almonium_book_processor.config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=120"]
