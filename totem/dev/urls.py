from django.urls import path

from . import views

app_name = "email"
urlpatterns = [
    path(
        "test/",
        views.rrule,
        name="rrule",
    ),
    path("healthcheck/", views.healthcheck, name="healthcheck"),
]
