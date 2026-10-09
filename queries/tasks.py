"""Celery adapter for AI search resolution (queries/services/resolution.py).

Owns the `QueryRequest` lifecycle and the retry policy:

- A `PermanentFailure` (bad credentials, a request Claude rejects) marks the
  request as errored at once.
- Anything else is retried up to QUERY_TASK_MAX_RETRIES times by re-queueing
  the task with exponential backoff and jitter, so the worker is free between
  attempts and a pending retry survives a worker restart.
- Re-running is harmless: a request that is already done or errored (for
  example a message delivered twice), or no longer exists, is left alone.
"""

import logging
import random
import time
from typing import cast

from celery import Task, shared_task
from django.conf import settings

from accounts.models import Profile
from queries.models import QueryRequest
from queries.services.resolution import PermanentFailure, default_resolver

logger = logging.getLogger(__name__)

_FINISHED = {QueryRequest.Status.DONE, QueryRequest.Status.ERROR}


def retry_delay_seconds(retries: int) -> float:
    """Exponential backoff with jitter: after the n-th failure (from 0), wait between half and all of base·2ⁿ."""
    ceiling = settings.QUERY_RETRY_BACKOFF_SECONDS * 2**retries
    return ceiling / 2 + random.uniform(0, ceiling / 2)


def _resolve_query(self: Task, query_request_id: int) -> None:
    log_context = {"query_request_id": query_request_id, "attempt": self.request.retries + 1}
    query_request = QueryRequest.objects.filter(id=query_request_id).first()
    if query_request is None:
        logger.info("query_request_gone", extra=log_context)  # deleted while queued (e.g. with its user)
        return
    if query_request.status in _FINISHED:
        logger.info("query_already_finished", extra=log_context | {"status": query_request.status})
        return
    if query_request.status != QueryRequest.Status.RUNNING:
        query_request.status = QueryRequest.Status.RUNNING
        query_request.save(update_fields=["status", "updated_at"])

    logger.info("query_attempt_started", extra=log_context)
    started = time.monotonic()
    try:
        profile = Profile.objects.filter(user_id=query_request.user_id).first()
        results = default_resolver().resolve(query_request.prompt, profile)
    except PermanentFailure as exc:
        _mark_failed(query_request, exc, log_context | {"retryable": False, "duration_ms": _elapsed_ms(started)})
        return
    except Exception as exc:
        if self.request.retries >= settings.QUERY_TASK_MAX_RETRIES:
            _mark_failed(query_request, exc, log_context | {"retryable": True, "duration_ms": _elapsed_ms(started)})
            return
        delay = retry_delay_seconds(self.request.retries)
        logger.warning("query_attempt_failed", exc_info=True, extra=log_context | {"retry_in_s": round(delay, 1)})
        raise self.retry(exc=exc, countdown=delay) from exc

    query_request.results = results
    query_request.status = QueryRequest.Status.DONE
    query_request.save(update_fields=["results", "status", "updated_at"])
    logger.info("query_resolution_succeeded", extra=log_context | {"duration_ms": _elapsed_ms(started)})


# shared_task is unannotated, and with arguments Pyright infers nonsense for it; state the type.
resolve_query = cast(
    Task,
    shared_task(name="queries.tasks.resolve_query", bind=True, max_retries=settings.QUERY_TASK_MAX_RETRIES)(
        _resolve_query
    ),
)


def _mark_failed(query_request: QueryRequest, exc: Exception, log_context: dict) -> None:
    query_request.status = QueryRequest.Status.ERROR
    query_request.error_message = str(exc)
    query_request.save(update_fields=["status", "error_message", "updated_at"])
    logger.error("query_resolution_failed", exc_info=exc, extra=log_context)


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
