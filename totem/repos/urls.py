from django.contrib.sitemaps import Sitemap
from django.urls import path, reverse

from .views import PromptListView

app_name = "repos"


class ReposSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        return ["repos:prompt-list"]

    def location(self, item):
        return reverse(item)


urlpatterns = [
    path("prompts/", view=PromptListView.as_view(), name="prompt-list"),
]
