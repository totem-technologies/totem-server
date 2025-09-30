from django.contrib.sitemaps import Sitemap
from django.urls import path

from totem.blog.models import BlogPost

from . import views

app_name = "blog"


class BlogSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        return BlogPost.objects.filter(publish=True)

    def lastmod(self, obj: BlogPost):
        return obj.date_modified


urlpatterns = [
    path("", views.BlogPostListView.as_view(), name="list"),
    path("<slug:slug>/social", views.post_social, name="post_social"),
    path("<slug:slug>/social/<str:image_format>.jpg", views.post_social_img, name="post_social_img"),
    path("<slug:slug>/", views.BlogPostDetailView.as_view(), name="detail"),
]
