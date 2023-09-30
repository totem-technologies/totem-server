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
    path("rsvp/<str:event_slug>/", views.rsvp, name="rsvp"),
    path("join/<str:event_slug>/", views.join, name="join"),
    path("event/<str:event_slug>/", views.event_detail, name="event_detail"),
    path("subscribe/<str:slug>/", views.subscribe, name="subscribe"),
    path("<str:slug>/", views.detail, name="detail"),
    # path("<str:slug>/event.ics", views.ics, name="ics"),
    # path("sitemap.xml", CirclesSitemap),
]
