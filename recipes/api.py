import logging
import time

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from recipes.models import Recipe
from recipes.services.keyword_search import search_recipes, search_terms

logger = logging.getLogger(__name__)


class RecipeOutSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recipe
        fields = [
            "id",
            "recipe_name",
            "source_url",
            "image_url",
            "calories_per_serving",
            "protein_g_per_serving",
            "carbs_g_per_serving",
            "fat_g_per_serving",
            "fiber_g_per_serving",
            "sugar_g_per_serving",
            "sodium_mg_per_serving",
        ]
        read_only_fields = fields


class SearchParamsSerializer(serializers.Serializer):
    # CharField trims whitespace and rejects blank, so "   " is a 400.
    q = serializers.CharField(max_length=200)


class SearchOutSerializer(serializers.Serializer):
    query = serializers.CharField()
    results = RecipeOutSerializer(many=True)
    elapsed_ms = serializers.FloatField()


class KeywordSearchView(APIView):
    @extend_schema(
        operation_id="recipes_keyword_search",
        parameters=[SearchParamsSerializer],
        responses={200: SearchOutSerializer, 400: None},
    )
    def get(self, request: Request) -> Response:
        """Search without AI: synchronous, at most KEYWORD_SEARCH_RESULT_COUNT recipes.
        `elapsed_ms` is database search time, measured here."""
        params = SearchParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        query = params.validated_data["q"]

        started = time.perf_counter()
        recipes = search_recipes(query, limit=settings.KEYWORD_SEARCH_RESULT_COUNT)
        elapsed_ms = (time.perf_counter() - started) * 1000

        logger.info(
            "keyword_search_completed",
            extra={"terms": len(search_terms(query)), "results": len(recipes), "duration_ms": round(elapsed_ms, 1)},
        )
        return Response(SearchOutSerializer({"query": query, "results": recipes, "elapsed_ms": elapsed_ms}).data)
