"""Celery adapter for AI search resolution (queries/services/resolution.py).

Owns the `QueryRequest` lifecycle and the retry policy:

- A `PermanentFailure` (bad credentials, a request the model provider rejects)
  or `ImproperlyConfigured` (e.g. no API key for AI_SEARCH_MODEL's provider)
  marks the request as errored at once.
- Anything else is retried up to QUERY_TASK_MAX_RETRIES times by re-queueing
  the task with exponential backoff and jitter, so the worker is free between
  attempts and a pending retry survives a worker restart.
- A retry that would start after the request's deadline isn't queued: the
  request ends as an error now rather than after a wasted wait.
- Re-running is harmless: a request that is already done or errored (for
  example a message delivered twice), past its deadline, or no longer exists,
  is left alone. The status changes themselves are QueryRequest's
  conditional transitions (queries/models.py), so a late attempt can't
  overwrite a finished request.
"""

import logging
import random
import time
from datetime import timedelta
from typing import cast

from celery import Task, shared_task
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from accounts.models import Profile
from queries.models import QueryRequest
from queries.services.resolution import PermanentFailure, default_resolver

logger = logging.getLogger(__name__)


def retry_delay_seconds(retries: int) -> float:
    """Exponential backoff with jitter: after the n-th failure (from 0), wait between half and all of base·2ⁿ."""
    ceiling = settings.QUERY_RETRY_BACKOFF_SECONDS * 2**retries
    return ceiling / 2 + random.uniform(0, ceiling / 2)


def worst_case_seconds() -> float:
    """Longest a request can take if every attempt times out and every backoff hits its ceiling
    (queueing excluded). QUERY_DEADLINE_SECONDS must cover it (checked by QueriesConfig.ready)."""
    retries = settings.QUERY_TASK_MAX_RETRIES
    attempts = (retries + 1) * settings.AI_SEARCH_MODEL_TIMEOUT_SECONDS
    backoff = sum(settings.QUERY_RETRY_BACKOFF_SECONDS * 2**n for n in range(retries))
    return attempts + backoff


def _resolve_query(self: Task, query_request_id: int) -> None:
    log_context = {"query_request_id": query_request_id, "attempt": self.request.retries + 1}
    query_request = QueryRequest.objects.filter(id=query_request_id).first()
    if query_request is None:
        logger.info("query_request_gone", extra=log_context)  # deleted while queued (e.g. with its user)
        return
    if not query_request.start():
        _log_already_ended(query_request, log_context)
        return

    logger.info("query_attempt_started", extra=log_context)
    started = time.monotonic()
    try:
        profile = Profile.objects.filter(user_id=query_request.user_id).first()
        results = default_resolver().resolve(query_request.prompt, profile)
    except (PermanentFailure, ImproperlyConfigured) as exc:
        _mark_failed(query_request, exc, log_context | {"retryable": False, "duration_ms": _elapsed_ms(started)})
        return
    except Exception as exc:
        delay = retry_delay_seconds(self.request.retries)
        out_of_time = timezone.now() + timedelta(seconds=delay) >= query_request.deadline
        if self.request.retries >= settings.QUERY_TASK_MAX_RETRIES or out_of_time:
            context = {"retryable": True, "deadline_reached": out_of_time, "duration_ms": _elapsed_ms(started)}
            _mark_failed(query_request, exc, log_context | context)
            return
        logger.warning("query_attempt_failed", exc_info=True, extra=log_context | {"retry_in_s": round(delay, 1)})
        raise self.retry(exc=exc, countdown=delay) from exc

    if not query_request.succeed(results):
        _log_already_ended(query_request, log_context, discarded_results=True)
        return
    logger.info("query_resolution_succeeded", extra=log_context | {"duration_ms": _elapsed_ms(started)})


# shared_task is unannotated, and with arguments Pyright infers nonsense for it; state the type.
resolve_query = cast(
    Task,
    shared_task(name="queries.tasks.resolve_query", bind=True, max_retries=settings.QUERY_TASK_MAX_RETRIES)(
        _resolve_query
    ),
)


def _mark_failed(query_request: QueryRequest, exc: Exception, log_context: dict) -> None:
    if query_request.fail(str(exc)):
        logger.error("query_resolution_failed", exc_info=exc, extra=log_context)
    else:
        _log_already_ended(query_request, log_context)


def _log_already_ended(query_request: QueryRequest, log_context: dict, discarded_results: bool = False) -> None:
    """Another writer got there first: the request finished, or expired at its deadline."""
    context = log_context | {"status": query_request.status, "discarded_results": discarded_results}
    if query_request.error_message == QueryRequest.EXPIRED_MESSAGE:
        logger.warning("query_expired", extra=context)
    else:
        logger.info("query_already_finished", extra=context)


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
