from django.urls import path
from django.views.generic import RedirectView, TemplateView

from . import views

app_name = "email"
urlpatterns = [
    path("waitlist/", views.WaitListAddView.as_view(), name="waitlist"),
    path("waitlist/survey/", TemplateView.as_view(template_name="email/waitlist_survey.html"), name="waitlist_survey"),
    path(
        "waitlist/<uuid:id>/subscribe/",
        views.WaitListSubscribeView.as_view(),
        name="waitlist_subscribe",
    ),
]
