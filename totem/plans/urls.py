from django.contrib.sitemaps import Sitemap
from django.urls import path

from . import views
from .models import CirclePlan

app_name = "plans"


class PlansSitemap(Sitemap):
    priority = 0.5
    changefreq = "monthly"

    def items(self):
        return sorted(CirclePlan.objects.filter(published=True), key=lambda x: x.date_modified)

    def lastmod(self, obj):
        return obj.date_modified


urlpatterns = [
    path("", views.PlanListView.as_view(), name="list"),
    path("<int:pk>/", views.PlanDetailView.as_view(), name="detail"),
    # path("plans/create/", views.PlanCreateView.as_view(), name="create"),
    # path("plans/<int:pk>/update/", views.PlanUpdateView.as_view(), name="update"),
    # path("plans/<int:pk>/delete/", views.PlanDeleteView.as_view(), name="delete"),
]
