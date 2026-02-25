from django.contrib.sitemaps import Sitemap
from django.urls import path, re_path, reverse
from django.views.generic import TemplateView

from . import views

proxied_site_pages = [
    "about",
    "crisis-resources",
    "docs/keeper-trainer-curriculum",
    "friends-of-totem",
    "guidelines",
    "how-it-works",
    "privacy-notice",
    "staying-grounded",
    "topics/lgbtq",
    "topics/love-and-other-emotions",
    "topics/mothers",
    "topics/self-improvement",
    "totem-for-introverts",
    "training",
    "why-totem",
]

proxied_site_patterns = [re_path(rf"^{page}/$", views.proxied_site_proxy, name=page) for page in proxied_site_pages]


class PagesSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        static_pages = [
            "home",
            "tos",
            "privacy",
            "team",
            "team-pam",
        ]
        return [f"pages:{page}" for page in static_pages + proxied_site_pages]

    def location(self, item):
        return reverse(item)


app_name = "pages"
urlpatterns = [
    path("", views.proxied_site_page, name="home"),
    path("team/", views.team_view, name="team"),
    # path("about/", TemplateView.as_view(template_name="pages/about.html"), name="about"),
    # path("how-it-works/", views.HowItWorksView.as_view(), name="how-it-works"),
    path("tos/", TemplateView.as_view(template_name="pages/tos.html"), name="tos"),
    path("privacy/", TemplateView.as_view(template_name="pages/privacy.html"), name="privacy"),
    path("keepers/<str:name>/", views.keepers, name="keepers"),
    path("team/pam/", TemplateView.as_view(template_name="pages/pam.html"), name="team-pam"),
    path("metrics/", TemplateView.as_view(template_name="pages/metrics.html"), name="metrics"),
    path(
        "thank-you-voting/", TemplateView.as_view(template_name="pages/thank_you_voting.html"), name="thank-you-voting"
    ),
    path(
        "robots.txt", TemplateView.as_view(template_name="pages/robots.txt", content_type="text/plain"), name="robots"
    ),
    path("r/<slug:slug>/qr/", views.redirect_qr, name="redirect_qr"),
    path("r/<slug:slug>/", views.redirect, name="redirect"),
    path("proxied-site/", views.dev_proxied_site_page, name="proxied-site"),
    path(
        "proxied-site/_test",
        views.proxied_site_page,
        name="proxied-site-test",
        kwargs={"page": "how-totem-works"},
    ),
    path("proxied-site/<path:page>/", views.dev_proxied_site_page, name="proxied-site-path"),
]

urlpatterns += proxied_site_patterns
