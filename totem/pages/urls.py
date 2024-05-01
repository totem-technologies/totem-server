from django.contrib.sitemaps import Sitemap
from django.urls import path, re_path, reverse
from django.views.generic import TemplateView

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
            "team-pam",
        ]
        return [f"pages:{page}" for page in pages]

    def location(self, item):
        return reverse(item)


webflow_pages = [
    "how-it-works",
    "about",
    "guidelines",
    "topics/mothers",
    "topics/lgbtq",
    "topics/creatives",
    "topics/self-improvement",
]

webflow_patterns = [re_path(rf"^{page}/", views.webflow_proxy, name=page) for page in webflow_pages]


app_name = "pages"
urlpatterns = [
    path("", views.webflow_page, name="home"),
    path("team/", views.team_view, name="team"),
    # path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    # path("how-it-works/", views.HowItWorksView.as_view(), name="how-it-works"),
    path("tos/", TemplateView.as_view(template_name="pages/tos.html"), name="tos"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("training/", views.training, name="training"),
    path("keepers/<str:name>/", views.keepers, name="keepers"),
    path("team/pam/", TemplateView.as_view(template_name="pages/pam.html"), name="team-pam"),
    path("metrics/", TemplateView.as_view(template_name="pages/metrics.html"), name="metrics"),
    path(
        "robots.txt", TemplateView.as_view(template_name="pages/robots.txt", content_type="text/plain"), name="robots"
    ),
    path("r/<slug:slug>/qr/", views.redirect_qr, name="redirect_qr"),
    path("r/<slug:slug>/", views.redirect, name="redirect"),
    path("webflow/", views.dev_webflow_page, name="webflow"),
    path("webflow/_test", views.webflow_page, name="webflow-test", kwargs={"page": "how-totem-works"}),
    path("webflow/<path:page>/", views.dev_webflow_page, name="webflow-path"),
]

urlpatterns += webflow_patterns
