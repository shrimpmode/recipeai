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
        from queries.services.model_providers import ModelSpec

        ModelSpec.parse(settings.AI_SEARCH_MODEL)
        from queries.tasks import worst_case_seconds

        # A deadline shorter than the retry policy would expire requests that are still being retried.
        if worst_case_seconds() > settings.QUERY_DEADLINE_SECONDS:
            raise ImproperlyConfigured(
                f"QUERY_DEADLINE_SECONDS ({settings.QUERY_DEADLINE_SECONDS:g}) must be at least the retry "
                f"worst case ({worst_case_seconds():g} s: attempts * model timeout + backoff)"
            )
        from queries.services import resolution  # noqa: F401  (connects its setting_changed receiver)
