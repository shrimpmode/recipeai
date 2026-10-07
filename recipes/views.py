import logging
import time

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import render

from recipes.services.keyword_search import search_recipes, search_terms

logger = logging.getLogger(__name__)


@login_required
def keyword_search(request):
    """Synchronous search without AI: it is a single query, so unlike
    `queries.views.submit_query` there is no Celery task or polling."""
    query = request.GET.get("q", "").strip()
    if not query:
        return HttpResponseBadRequest("Search text is required.")

    started = time.perf_counter()
    recipes = search_recipes(query, limit=settings.KEYWORD_SEARCH_RESULT_COUNT)
    elapsed_ms = (time.perf_counter() - started) * 1000

    logger.info(
        "keyword_search_completed",
        extra={"terms": len(search_terms(query)), "results": len(recipes), "duration_ms": round(elapsed_ms, 1)},
    )
    return render(
        request,
        "recipes/_search_results.html",
        {"query": query, "recipes": recipes, "elapsed_ms": elapsed_ms},
    )
