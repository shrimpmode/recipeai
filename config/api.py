"""URL map of the JSON API, mounted at /api/ (config/urls.py).

Paths have no trailing slash, as the frontend's generated client expects."""

from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from accounts.api import GoalsView, auth_urls
from queries.api import QueryStatusView, SubmitQueryView
from recipes.api import KeywordSearchView

urlpatterns = [
    path("auth/", include(auth_urls)),
    path("profile", GoalsView.as_view()),
    path("queries", SubmitQueryView.as_view()),
    path("queries/<int:query_request_id>", QueryStatusView.as_view()),
    path("search", KeywordSearchView.as_view()),
]

if settings.DEBUG:
    # The frontend's types come from `manage.py spectacular` (pnpm gen:api); serving the schema and
    # Swagger UI is a dev convenience only.
    urlpatterns += [
        path("schema", SpectacularAPIView.as_view(), name="api-schema"),
        path("docs", SpectacularSwaggerView.as_view(url_name="api-schema")),
    ]
