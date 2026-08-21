from django.contrib import admin

from queries.models import QueryRequest


@admin.register(QueryRequest)
class QueryRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "prompt", "created_at")
    list_filter = ("status",)
