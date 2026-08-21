from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, render

from queries.models import QueryRequest
from queries.tasks import resolve_query


@login_required
def submit_query(request):
    if request.method == "POST":
        prompt = request.POST.get("prompt", "").strip()
        if not prompt:
            return HttpResponseBadRequest("Prompt is required.")
        query_request = QueryRequest.objects.create(user=request.user, prompt=prompt)
        resolve_query.delay(query_request.id)
        return render(request, "queries/_status_poll.html", {"query_request": query_request})

    return render(request, "queries/submit.html")


@login_required
def query_status(request, query_request_id):
    query_request = get_object_or_404(QueryRequest, id=query_request_id, user=request.user)

    if query_request.status == QueryRequest.Status.DONE:
        return render(request, "queries/_results.html", {"query_request": query_request})
    if query_request.status == QueryRequest.Status.ERROR:
        return render(request, "queries/_error.html", {"query_request": query_request})
    return render(request, "queries/_status_poll.html", {"query_request": query_request})
