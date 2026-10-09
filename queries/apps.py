from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


class QueriesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "queries"

    def ready(self) -> None:
        # A typo in an adapter path should stop startup, not fail the first AI search.
        for name in ("AI_SEARCH_EMBEDDER", "AI_SEARCH_PICKER"):
            try:
                import_string(getattr(settings, name))
            except ImportError as exc:
                raise ImproperlyConfigured(f"{name}: {exc}") from exc
        from queries.services import resolution  # noqa: F401  (connects its setting_changed receiver)
