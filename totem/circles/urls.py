from django.contrib.sitemaps import Sitemap
from django.urls import path

from . import views
from .models import CircleEvent

app_name = "circles"


class SpacesSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        return CircleEvent.objects.filter(cancelled=False, open=True, listed=True, circle__published=True)

    def lastmod(self, obj: CircleEvent):
        return obj.date_modified


urlpatterns = [
    path("", views.list, name="list"),
    path("rsvp/<str:event_slug>/", views.rsvp, name="rsvp"),
    path("join/<str:event_slug>/", views.join, name="join"),
    path("event/<str:event_slug>/", views.event_detail, name="event_detail"),
    path("event/<str:event_slug>/social", views.event_social, name="event_social"),
    path("event/<str:event_slug>/social/<str:image_format>.jpg", views.event_social_img, name="event_social_img"),
    path("calendar/<str:event_slug>/", views.calendar, name="calendar"),
    path("subscribe/<str:slug>/", views.subscribe, name="subscribe"),
    path("topic/<slug:slug>/", views.topic, name="topic"),
    path("<str:slug>/", views.detail, name="detail"),
    # path("<str:slug>/event.ics", views.ics, name="ics"),
    # path("sitemap.xml", CirclesSitemap),
]
