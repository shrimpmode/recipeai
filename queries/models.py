from django.conf import settings
from django.db import models


class QueryRequest(models.Model):
    """One user prompt and its resolution lifecycle.

    `results`, once status is DONE, holds exactly RESULT_COUNT dicts of the
    shape produced by `queries.tasks._serialize_result`.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    # Declared for Pyright, which can't see Django's implicit fields (mypy's plugin can).
    id: int
    user_id: int

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="query_requests")
    prompt = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    results = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"QueryRequest({self.id}, {self.status})"
