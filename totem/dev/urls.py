from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "dev"
urlpatterns = [
    path(
        "test/",
        views.rrule,
        name="rrule",
    ),
    path("healthcheck/", views.healthcheck, name="healthcheck"),
    path("widgets/", TemplateView.as_view(template_name="dev/widgets.html"), name="widgets"),
]
