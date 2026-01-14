from django.contrib.sitemaps import Sitemap
from django.urls import path
from django.utils import timezone
from django.views.generic import RedirectView

from . import views
from .models import Session

app_name = "spaces"


class SpacesSitemap(Sitemap):
    priority = 0.5
    changefreq = "daily"

    def items(self):
        return Session.objects.filter(
            start__gte=timezone.now(), cancelled=False, open=True, listed=True, space__published=True
        )

    def lastmod(self, obj: Session):
        return obj.date_modified


urlpatterns = [
    path("", views.spaces, name="list"),
    path("sessions/", views.sessions, name="sessions"),
    path("rsvp/<str:session_slug>/", views.rsvp, name="rsvp"),
    path("join/<str:session_slug>/", views.join, name="join"),
    path("session/<str:session_slug>/", views.session_detail, name="session_detail"),
    path("session/<str:session_slug>/social/", views.session_social, name="session_social"),
    path(
        "session/<str:session_slug>/social/<str:image_format>.jpg", views.session_social_img, name="session_social_img"
    ),
    path("calendar/<str:session_slug>/", views.calendar, name="calendar"),
    path("subscribe/<str:slug>/", views.subscribe, name="subscribe"),
    # Legacy redirects for old URLs (circles -> spaces rename) - must be before the catch-all <str:slug>/
    path("events/", RedirectView.as_view(pattern_name="spaces:sessions", permanent=True), name="events_redirect"),
    path("event/<str:event_slug>/", views.event_detail_redirect, name="event_detail_redirect"),
    # Catch-all for space detail - must be last
    path("<str:slug>/", views.detail, name="detail"),
]
