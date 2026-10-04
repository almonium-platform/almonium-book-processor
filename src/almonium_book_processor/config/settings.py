from __future__ import annotations

import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parents[3]


def env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [value.strip() for value in os.getenv(name, default).split(",") if value.strip()]


DEBUG = env_bool("DEBUG", True)
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-local-development-key")
if not DEBUG and SECRET_KEY == "unsafe-local-development-key":
    raise RuntimeError("SECRET_KEY must be configured when DEBUG is false")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "almonium_book_processor.catalog",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "almonium_book_processor.config.urls"
WSGI_APPLICATION = "almonium_book_processor.config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=60,
        conn_health_checks=True,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 100 * 1024 * 1024

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAdminUser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Almonium Book Service",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "amqp://guest:guest@localhost:5672//")
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = int(os.getenv("CELERY_TASK_TIME_LIMIT", "7200"))
CELERY_TASK_SOFT_TIME_LIMIT = int(os.getenv("CELERY_TASK_SOFT_TIME_LIMIT", "6900"))
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_EAGER_PROPAGATES = True

# One pretrained spaCy pipeline for every language spaCy ships one for, keyed
# by the registry code (Norwegian is "no" here and Bokmål "nb" in spaCy). Each
# is pinned in the worker extra; NLP_SPACY_MODEL_<CODE> swaps a model's size,
# not its language. A language absent here cannot have its vocabulary analyzed.
_SPACY_DEFAULT_MODELS = {
    "ca": "ca_core_news_sm",
    "da": "da_core_news_sm",
    "de": "de_core_news_sm",
    "el": "el_core_news_sm",
    "en": "en_core_web_sm",
    "es": "es_core_news_sm",
    "fi": "fi_core_news_sm",
    "fr": "fr_core_news_sm",
    "hr": "hr_core_news_sm",
    "it": "it_core_news_sm",
    "ja": "ja_core_news_sm",
    "ko": "ko_core_news_sm",
    "lt": "lt_core_news_sm",
    "mk": "mk_core_news_sm",
    "nl": "nl_core_news_sm",
    "no": "nb_core_news_sm",
    "pl": "pl_core_news_sm",
    "pt": "pt_core_news_sm",
    "ro": "ro_core_news_sm",
    "ru": "ru_core_news_sm",
    "sl": "sl_core_news_sm",
    "sv": "sv_core_news_sm",
    "uk": "uk_core_news_sm",
    "zh": "zh_core_web_sm",
}
NLP_SPACY_MODELS = {
    language: os.getenv(f"NLP_SPACY_MODEL_{language.upper()}", model)
    for language, model in _SPACY_DEFAULT_MODELS.items()
}
NLP_EMBEDDING_MODEL = os.getenv(
    "NLP_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_ALIGNMENT_PRIMARY_MODEL = os.getenv("OPENAI_ALIGNMENT_PRIMARY_MODEL", "gpt-5.6-luna")
OPENAI_ALIGNMENT_ESCALATION_MODEL = os.getenv("OPENAI_ALIGNMENT_ESCALATION_MODEL", "gpt-5.6-terra")
OPENAI_ALIGNMENT_CONFIDENCE = float(os.getenv("OPENAI_ALIGNMENT_CONFIDENCE", "0.80"))
# Translation is the product text a learner reads, so it defaults to the stronger
# tier: the whole-book difference is under a dollar at Batch prices.
OPENAI_TRANSLATION_QUALITY_MODEL = os.getenv("OPENAI_TRANSLATION_QUALITY_MODEL", "gpt-5.6-terra")
OPENAI_TRANSLATION_DRAFT_MODEL = os.getenv("OPENAI_TRANSLATION_DRAFT_MODEL", "gpt-5.6-luna")
# A translation review's seats beside the Claude Code reviewer, as "provider:model" with
# provider codex or claude-code (the plans) or openai (the metered API). The second reviewer is
# from another vendor than the first on purpose. The adjudicator is neither reviewer and must
# not be the model that wrote the translation, which defends its own text: the first of these
# candidates that did not translate the edition rules on it.
# A third part sets the reasoning effort of the seat's review. GPT-6.1-sol reviews at medium:
# on three chapters it found as much as at high effort, ten of high's eleven material
# findings among them, on a quarter of the tokens and in a sixth of the time.
TRANSLATION_OUTSIDE_REVIEWER = os.getenv("TRANSLATION_OUTSIDE_REVIEWER", "codex:gpt-6.1-sol:medium")
TRANSLATION_ADJUDICATORS = os.getenv(
    "TRANSLATION_ADJUDICATORS", "codex:gpt-6-astra,claude-code:fable"
)
# Who writes a level adaptation, as a seat (see ai/seats.py): chapter pilots, floor probes and
# whole books. Empty means the API's quality model, which is what a deployed worker uses; the
# owner's machine names a plan seat, e.g. codex:gpt-6-astra.
ADAPTATION_GENERATOR = os.getenv("ADAPTATION_GENERATOR", "")

# The blind difficulty judges of a chapter pilot, and so of a floor probe, as seats separated
# by commas. Each judge reads the text DIFFICULTY_READINGS times and its middle reading counts;
# the pilot's level is the highest of the judges'. Empty means the chapter-analysis model
# alone, read once: on 2026-10-04 that model called B1 attempts and B2 adaptations alike B2,
# where Opus and GPT-6.1-sol told them apart, so the owner's machine names those two.
DIFFICULTY_JUDGES = os.getenv("DIFFICULTY_JUDGES", "")
# The fidelity auditors of a chapter pilot, as seats separated by commas. With two, each reads
# the whole pilot, and a material finding only one of them raised holds the gate only if the
# other confirms it. Empty means the API tier's model alone, as before.
FIDELITY_AUDITORS = os.getenv("FIDELITY_AUDITORS", "")
DIFFICULTY_READINGS = int(os.getenv("DIFFICULTY_READINGS", "3"))

# A task that calls a plan seat can only run where the plan's CLI is signed in. It is sent to
# a queue of its own, which the container worker never takes and the owner's host worker does
# (./plan-worker). The adaptation tasks generate, judge and audit, so a plan seat in any of
# those three settings sends them there. With no plan seat configured nothing is routed.
PLAN_QUEUE = "plans"


def plan_task_routes(*seat_settings: str) -> dict[str, dict[str, str]]:
    seats = [seat.strip() for setting in seat_settings for seat in setting.split(",")]
    if not any(seat.partition(":")[0] in ("codex", "claude-code") for seat in seats):
        return {}
    return {
        f"almonium_book_processor.catalog.tasks.{task}": {"queue": PLAN_QUEUE}
        for task in ("adapt_chapter_pilot", "adapt_book", "run_floor_probe")
    }


CELERY_TASK_ROUTES = plan_task_routes(ADAPTATION_GENERATOR, DIFFICULTY_JUDGES, FIDELITY_AUDITORS)
# Private-import metadata is one small call per book; the cheaper tier is plenty.
OPENAI_METADATA_MODEL = os.getenv("OPENAI_METADATA_MODEL", "gpt-5.6-luna")
# The fidelity audit reads adapted text beside its source; "quality" is the
# translation quality model, "draft" the cheaper tier, about a tenth the cost.
OPENAI_FIDELITY_TIER = os.getenv("OPENAI_FIDELITY_TIER", "quality")
OPENAI_BATCH_POLL_SECONDS = int(os.getenv("OPENAI_BATCH_POLL_SECONDS", "60"))

# The Claude Code CLI on the owner's subscription, for output-heavy generation
# run from the owner's machine. Never set on a deployed worker: the CLI needs a
# login that exists only where the owner is signed in.
CLAUDE_CODE_BINARY = os.getenv("CLAUDE_CODE_BINARY", "claude")
CLAUDE_CODE_MODEL = os.getenv("CLAUDE_CODE_MODEL", "opus")
CLAUDE_CODE_TIMEOUT_SECONDS = float(os.getenv("CLAUDE_CODE_TIMEOUT_SECONDS", "1800"))
CLAUDE_CODE_WORKERS = int(os.getenv("CLAUDE_CODE_WORKERS", "4"))
# The Codex CLI on the owner's ChatGPT plan, for the same owner-machine jobs. Name the binary
# explicitly when an old one is first on the path: 0.114 cannot refresh the login.
CODEX_BINARY = os.getenv("CODEX_BINARY", "codex")
CODEX_TRANSLATION_MODEL = os.getenv("CODEX_TRANSLATION_MODEL", "gpt-6-astra")
CODEX_TIMEOUT_SECONDS = float(os.getenv("CODEX_TIMEOUT_SECONDS", "1800"))
CODEX_WORKERS = int(os.getenv("CODEX_WORKERS", "4"))

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", not DEBUG)
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
