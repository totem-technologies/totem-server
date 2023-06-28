from django.contrib.sitemaps import Sitemap
from django.urls import path, reverse
from django.views.generic import RedirectView, TemplateView

from . import views


class PagesSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        pages = [
            "home",
            "about",
            "tos",
            "privacy",
            "team",
            "how-it-works",
            "keepers-gabe",
            "keepers-heather",
            "team-pam",
        ]
        return [f"pages:{page}" for page in pages]

    def location(self, item):
        return reverse(item)


app_name = "pages"
urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("team/", views.TeamView.as_view(), name="team"),
    path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    path("how-it-works/", views.HowItWorksView.as_view(), name="how-it-works"),
    path("tos/", TemplateView.as_view(template_name="pages/tos.html"), name="tos"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("privacy-policy/", RedirectView.as_view(pattern_name="pages:privacy"), name="privacy-policy"),
    path("keepers/gabe/", TemplateView.as_view(template_name="pages/keepers/gabe.html"), name="keepers-gabe"),
    path("keepers/heather/", TemplateView.as_view(template_name="pages/keepers/heather.html"), name="keepers-heather"),
    # path("keepers/josie/", TemplateView.as_view(template_name="pages/keepers/josie.html"), name="keepers-josie"),
    path("team/pam/", TemplateView.as_view(template_name="pages/pam.html"), name="team-pam"),
    path("metrics/", TemplateView.as_view(template_name="pages/metrics.html"), name="metrics"),
]
