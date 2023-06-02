from django.urls import path
from django.views.generic import RedirectView, TemplateView

from . import views

app_name = "email"
urlpatterns = [
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
]
