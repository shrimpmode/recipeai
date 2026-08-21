from django.urls import path

from queries import views

urlpatterns = [
    path("", views.submit_query, name="submit-query"),
    path("queries/<int:query_request_id>/status/", views.query_status, name="query-status"),
]
