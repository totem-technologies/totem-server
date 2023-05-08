from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "pages"
urlpatterns = [
    path("team/", views.TeamView.as_view(), name="team"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("how-it-works/", views.HowItWorksView.as_view(), name="how-it-works"),
    path("tos/", TemplateView.as_view(template_name="pages/tos.html"), name="tos"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("keepers/gabe", TemplateView.as_view(template_name="pages/keepers/gabe.html"), name="keepers-gabe"),
    path("keepers/heather", TemplateView.as_view(template_name="pages/keepers/heather.html"), name="keepers-heather"),
    path("team/pam", TemplateView.as_view(template_name="pages/pam.html"), name="team-pam"),
    path("participate/", view=views.ParticipateView.as_view(), name="participate"),
    path("participate/onboard", view=views.ParticipateOnboardView.as_view(), name="participate-onboard"),
]
