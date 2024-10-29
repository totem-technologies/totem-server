from django.urls import path
from django.views.generic.base import RedirectView

from . import views

app_name = "email"
urlpatterns = [
    path("", RedirectView.as_view(pattern_name="email:template")),
    path(
        "subscribe/<uuid:id>/",
        views.SubscribeView.as_view(),
        name="subscribe",
    ),
    path(
        "unsubscribe/<uuid:id>/",
        views.UnsubscribeView.as_view(),
        name="unsubscribe",
    ),
    path("templates/", views.template_view, name="template"),
    path("templates/<str:name>/", views.template_view, name="template"),
]
