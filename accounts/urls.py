from django.urls import path

from accounts import views

urlpatterns = [
    path("", views.edit_profile, name="edit-profile"),
]
