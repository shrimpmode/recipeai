from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from config.rest import request_user
from queries.models import QueryRequest
from queries.tasks import resolve_query


class QueryInSerializer(serializers.Serializer):
    # CharField trims whitespace and rejects blank, so "   " is a 400.
    prompt = serializers.CharField(max_length=1000)


class ResultOutSerializer(serializers.Serializer):
    """One entry of `QueryRequest.results` (see `queries.tasks._serialize_result`)."""

    recipe_id = serializers.IntegerField()
    recipe_name = serializers.CharField()
    description = serializers.CharField()
    source_url = serializers.CharField()
    image_url = serializers.CharField(allow_null=True)
    calories_per_serving = serializers.FloatField(allow_null=True)
    protein_g_per_serving = serializers.FloatField(allow_null=True)
    carbs_g_per_serving = serializers.FloatField(allow_null=True)
    fat_g_per_serving = serializers.FloatField(allow_null=True)
    fiber_g_per_serving = serializers.FloatField(allow_null=True)
    sugar_g_per_serving = serializers.FloatField(allow_null=True)
    sodium_mg_per_serving = serializers.FloatField(allow_null=True)


class QueryOutSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=QueryRequest.Status.choices)
    results = ResultOutSerializer(many=True, allow_null=True)
    # Set once the request is finished (done or error): submit-to-finish time, queueing included.
    elapsed_seconds = serializers.FloatField(allow_null=True)


def _query_out(query_request: QueryRequest) -> dict:
    finished = query_request.status in (QueryRequest.Status.DONE, QueryRequest.Status.ERROR)
    return QueryOutSerializer(
        {
            "id": query_request.id,
            "status": query_request.status,
            "results": query_request.results if query_request.status == QueryRequest.Status.DONE else None,
            "elapsed_seconds": query_request.elapsed_seconds if finished else None,
        }
    ).data


class SubmitQueryView(APIView):
    @extend_schema(
        operation_id="queries_submit_query",
        request=QueryInSerializer,
        responses={202: QueryOutSerializer, 400: None},
    )
    def post(self, request: Request) -> Response:
        """Queue an AI search; poll `GET /api/queries/{id}` until status is done or error.
        The error text is logged server-side, not returned: it can contain provider details."""
        payload = QueryInSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        query_request = QueryRequest.objects.create(user=request_user(request), prompt=payload.validated_data["prompt"])
        resolve_query.delay(query_request.id)
        query_request.refresh_from_db()  # eager Celery (tests) may already have resolved it
        return Response(_query_out(query_request), status=status.HTTP_202_ACCEPTED)


class QueryStatusView(APIView):
    @extend_schema(operation_id="queries_query_status", responses=QueryOutSerializer)
    def get(self, request: Request, query_request_id: int) -> Response:
        query_request = get_object_or_404(QueryRequest, id=query_request_id, user=request_user(request))
        return Response(_query_out(query_request))
