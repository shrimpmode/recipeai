import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key")
DEBUG = os.environ.get("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",  # OpenAPI schema for the frontend's generated types (pnpm gen:api)
    "django.contrib.postgres",  # needed for OpClass in index expressions (recipes trigram indexes)
    "pgvector.django",
    "accounts",
    "recipes",
    "queries",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "nutrition"),
        "USER": os.environ.get("POSTGRES_USER", "nutrition"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "nutrition"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
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

STATIC_URL = "static/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Frontend -------------------------------------------------------------
# Origins of the Next.js app (frontend/). It proxies /api to Django, so requests
# arrive with the frontend's Origin header; Django's CSRF check must trust it.
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("FRONTEND_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

# --- JSON API (Django REST Framework) -------------------------------------
# JSON only, session auth (CSRF-checked) and login required unless a view opts out.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["config.rest.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Nutrition API",
    "VERSION": "1",
    "SERVE_INCLUDE_SCHEMA": False,
    # Separate request/response components, so response fields are all marked required.
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {"QueryStatus": "queries.models.QueryRequest.Status"},
}

# --- Logging ------------------------------------------------------------
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise ImproperlyConfigured(f"LOG_LEVEL must be a standard logging level, got {LOG_LEVEL!r}")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "kv": {
            "()": "config.logging.KeyValueFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "kv"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        # Django's default config also logs to console; don't print those twice.
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        # Per-request chatter from the HTTP and model-loading libraries.
        "httpx": {"level": "WARNING"},
        "huggingface_hub": {"level": "WARNING"},
        "sentence_transformers": {"level": "WARNING"},
    },
}

# --- Celery -----------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "false").lower() == "true"
# Off: with it on, eager mode re-raises the task's Retry instead of running the retry. resolve_query
# records its own failures, and Celery still logs any unexpected task crash.
CELERY_TASK_EAGER_PROPAGATES = False
# Use LOGGING above in the worker too, instead of Celery replacing the root logger.
CELERY_WORKER_HIJACK_ROOT_LOGGER = False

# --- External APIs ------------------------------------------------------
# Only the provider named in AI_SEARCH_MODEL needs its key (checked when a worker first builds the model).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Embeddings run locally via sentence-transformers (see recipes/services/embeddings.py) -
# no API key needed. 384 is all-MiniLM-L6-v2's native output size.
EMBEDDING_DIMENSIONS = 384

# --- RAG pipeline tuning --------------------------------------------------
RETRIEVAL_CANDIDATE_COUNT = 15
RETRIEVAL_RERANKED_COUNT = 5
RESULT_COUNT = 3

# --- AI search resolution (queries/services/resolution.py) ----------------
# Adapters at the resolver's two seams; tests swap in queries.tests.fakes.
# Checked at startup (QueriesConfig.ready).
AI_SEARCH_EMBEDDER = "recipes.services.embeddings.LocalEmbedder"
AI_SEARCH_PICKER = "queries.services.generation.LLMPicker"
# The LLM behind LLMPicker, as "provider:model" (providers: queries/services/model_providers.py).
AI_SEARCH_MODEL = os.environ.get("AI_SEARCH_MODEL", "anthropic:claude-haiku-4-5-20251001")
# One model call; the SDK's own retries are off (the Celery task retries).
AI_SEARCH_MODEL_TIMEOUT_SECONDS = float(os.environ.get("AI_SEARCH_MODEL_TIMEOUT_SECONDS", "30"))
# Retries after the first attempt, re-queued with backoff of ~2, 4, 8 s (with jitter).
QUERY_TASK_MAX_RETRIES = 3
QUERY_RETRY_BACKOFF_SECONDS = 2.0
# How long a query request may stay unfinished before it ends as an error, stamped on each
# request at submit. Checked at startup to cover the worst case of the retries above.
QUERY_DEADLINE_SECONDS = float(os.environ.get("QUERY_DEADLINE_SECONDS", "150"))

# --- Keyword search (no AI) -----------------------------------------------
KEYWORD_SEARCH_RESULT_COUNT = 5
