from django.urls import path

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
    path("", views.list, name="list"),
    path("<str:slug>/event.ics", views.ics, name="ics"),
    path("<str:event_slug>/rsvp", views.rsvp, name="rsvp"),
    path("<str:slug>/", views.detail, name="detail"),
    path("<str:slug>/event/<str:event_slug>/", views.detail, name="event_detail"),
    # path("sitemap.xml", CirclesSitemap),
]
