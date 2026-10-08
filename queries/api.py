from typing import Annotated

from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema
from ninja.security import django_auth

from queries.models import QueryRequest
from queries.tasks import resolve_query

router = Router(tags=["ai-search"], auth=django_auth)


class QueryIn(Schema):
    prompt: Annotated[str, Field(min_length=1, max_length=1000, pattern=r"\S")]


class ResultOut(Schema):
    """One entry of `QueryRequest.results` (see `queries.tasks._serialize_result`)."""

    recipe_id: int
    recipe_name: str
    description: str
    source_url: str
    image_url: str | None
    calories_per_serving: float | None
    protein_g_per_serving: float | None
    carbs_g_per_serving: float | None
    fat_g_per_serving: float | None
    fiber_g_per_serving: float | None
    sugar_g_per_serving: float | None
    sodium_mg_per_serving: float | None


class QueryOut(Schema):
    id: int
    status: QueryRequest.Status
    results: list[ResultOut] | None
    # Set once the request is finished (done or error): submit-to-finish time, queueing included.
    elapsed_seconds: float | None


def _query_out(query_request: QueryRequest) -> QueryOut:
    finished = query_request.status in (QueryRequest.Status.DONE, QueryRequest.Status.ERROR)
    return QueryOut(
        id=query_request.id,
        status=QueryRequest.Status(query_request.status),
        results=query_request.results if query_request.status == QueryRequest.Status.DONE else None,
        elapsed_seconds=query_request.elapsed_seconds if finished else None,
    )


@router.post("", response={202: QueryOut})
def submit_query(request, payload: QueryIn):
    """Queue an AI search; poll `GET /api/queries/{id}` until status is done or error.
    The error text is logged server-side, not returned: it can contain provider details."""
    prompt = payload.prompt.strip()
    query_request = QueryRequest.objects.create(user=request.user, prompt=prompt)
    resolve_query.delay(query_request.id)
    query_request.refresh_from_db()  # eager Celery (tests) may already have resolved it
    return 202, _query_out(query_request)


@router.get("/{query_request_id}", response=QueryOut)
def query_status(request, query_request_id: int):
    query_request = get_object_or_404(QueryRequest, id=query_request_id, user=request.user)
    return _query_out(query_request)
