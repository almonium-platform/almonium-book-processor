FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --create-home app

COPY pyproject.toml README.md ./
COPY src ./src
COPY manage.py ./

RUN python -m pip install --no-cache-dir '.[worker]' && \
    DEBUG=false \
    SECRET_KEY=build-only-secret-key-not-used-at-runtime \
    ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput && \
    mkdir -p /app/media && \
    chown -R app:app /app

USER app

EXPOSE 8000

CMD ["gunicorn", "almonium_book_processor.config.wsgi:application", "--bind=0.0.0.0:8000", "--workers=2", "--timeout=120"]
