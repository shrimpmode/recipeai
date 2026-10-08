from django.contrib import admin
from django.urls import path

from config import views
from config.api import api

# The user-facing UI is the Next.js app in frontend/; Django serves the JSON API,
# the admin, and the staff-only engineering manual.
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", api.urls),
    path("docs/", views.manual, name="manual"),
]
