from django.contrib.sitemaps import Sitemap
from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "circles"


# class CirclesSitemap(Sitemap):
#     priority = 0.5
#     changefreq = "daily"

#     def items(self):
#         return Circles.objects.filter(published=True)

#     def lastmod(self, obj):
#         return obj.date_modified


urlpatterns = [
    path("", TemplateView.as_view(template_name="circles/list.html"), name="list"),
    path("<str:slug>/", views.detail, name="detail"),
    # path("sitemap.xml", CirclesSitemap),
]
