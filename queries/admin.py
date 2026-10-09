from django.contrib import admin

from queries.models import QueryRequest


@admin.register(QueryRequest)
class QueryRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "prompt", "created_at", "finished_at")
    list_filter = ("status",)
    # Status changes go through QueryRequest's transitions, never a hand edit.
    readonly_fields = ("status", "results", "error_message", "created_at", "expires_at", "finished_at")
