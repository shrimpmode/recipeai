from django.urls import path

from recipes import views

urlpatterns = [
    path("", views.keyword_search, name="keyword-search"),
]
