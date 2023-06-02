from django.urls import path
from django.views.generic import TemplateView

from .views import OnboardView

app_name = "onboard"
urlpatterns = [
    path("", view=OnboardView.as_view(), name="index"),
    path("sent/", TemplateView.as_view(template_name="onboard/email_sent.html"), name="sent"),
]
