from django.conf import settings
from ninja import NinjaAPI

from accounts.api import auth_router, profile_router
from queries.api import router as queries_router
from recipes.api import router as search_router

api = NinjaAPI(
    title="Nutrition API",
    version="1",
    urls_namespace="api",
    # The OpenAPI schema stays on (the frontend's types are generated from it); the Swagger UI is dev-only.
    docs_url="/docs" if settings.DEBUG else None,
)
api.add_router("/auth", auth_router)
api.add_router("/profile", profile_router)
api.add_router("/queries", queries_router)
api.add_router("/search", search_router)
