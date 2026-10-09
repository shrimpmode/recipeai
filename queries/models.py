from datetime import datetime, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


def _default_expiry() -> datetime:
    return timezone.now() + timedelta(seconds=settings.QUERY_DEADLINE_SECONDS)


class QueryRequest(models.Model):
    """One AI search and its lifecycle: pending → running → done | error.

    The transition methods are the only way to change `status`. Each is a
    conditional update on an unfinished row, so a late or duplicate attempt
    can't overwrite a finished request; each returns whether it took effect.

    Every request has a deadline (`expires_at`, stamped at submit from
    QUERY_DEADLINE_SECONDS). Past it, the request can only end as an error:
    whoever looks first (the poll endpoint or the worker) expires it, so a
    request whose worker died still finishes.

    `results`, once DONE, holds exactly RESULT_COUNT dicts of the shape built
    by `queries.services.resolution._result`.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        ERROR = "error", "Error"

    UNFINISHED = (Status.PENDING, Status.RUNNING)
    EXPIRED_MESSAGE = "expired: no result before the deadline"

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
    # Nullable only while rows written before 0002 exist; 0003 backfills them.
    # TODO(contract): make both NOT NULL once every deployed web process sets expires_at.
    expires_at = models.DateTimeField(null=True, default=_default_expiry)
    finished_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"QueryRequest({self.id}, {self.status})"

    @property
    def is_finished(self) -> bool:
        return self.status not in self.UNFINISHED

    @property
    def deadline(self) -> datetime:
        return self.expires_at or self.created_at + timedelta(seconds=settings.QUERY_DEADLINE_SECONDS)

    @property
    def elapsed_seconds(self) -> float | None:
        """Submit-to-finish time, queueing included (what the user waited); None until finished."""
        if self.finished_at is None:
            return None
        return (self.finished_at - self.created_at).total_seconds()

    def is_overdue(self, now: datetime | None = None) -> bool:
        return not self.is_finished and (now or timezone.now()) >= self.deadline

    def start(self) -> bool:
        """Mark running (again, on a retry). False if finished or overdue (then it is expired)."""
        if self.expire_if_overdue():
            return False
        return self._transition(self.Status.RUNNING)

    def succeed(self, results: list[dict]) -> bool:
        """Store the results. False if already finished or overdue (then it is expired instead)."""
        if self.expire_if_overdue():
            return False
        return self._transition(self.Status.DONE, results=results, finished_at=timezone.now())

    def fail(self, message: str) -> bool:
        """End with an error. The message is for logs and admins, never the API (it can hold provider details)."""
        return self._transition(self.Status.ERROR, error_message=message, finished_at=timezone.now())

    def expire_if_overdue(self, now: datetime | None = None) -> bool:
        """End an unfinished request past its deadline. True if this call expired it.

        It finished at its deadline, not whenever someone happened to look, so elapsed time
        reads as the full wait the user was promised."""
        if not self.is_overdue(now):
            return False
        return self._transition(self.Status.ERROR, error_message=self.EXPIRED_MESSAGE, finished_at=self.deadline)

    def _transition(self, status: Status, **fields) -> bool:
        changes = {"status": status, "updated_at": timezone.now(), **fields}
        updated = QueryRequest.objects.filter(pk=self.pk, status__in=self.UNFINISHED).update(**changes)
        if updated:
            for name, value in changes.items():
                setattr(self, name, value)
        else:
            self.refresh_from_db()
        return bool(updated)
