import base64
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect as django_redirect
from django.shortcuts import render
from django.views.generic import TemplateView

from ..users.models import User
from .models import Redirect
from .proxied_site import ProxiedSiteUnavailable, get_proxied_site_page
from .qrmaker import make_qr


@dataclass
class Step:
    title: str
    description: str
    image: str

    def url(self):
        return f"images/steps/{self.image}"


class HowItWorksView(TemplateView):
    template_name = "pages/how_it_works.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


def keepers(request, name):
    try:
        user = User.objects.get(email=f"{name}@totem.org")
    except User.DoesNotExist:
        raise Http404
    return django_redirect(to=user.get_keeper_url())


def redirect(request, slug):
    try:
        redirect = Redirect.get_by_slug(slug)
    except Redirect.DoesNotExist:
        raise Http404
    redirect.increment_count()
    parsed = urlparse(redirect.url)
    params = parse_qsl(parsed.query)
    params.extend(
        [
            ("utm_source", "redirect"),
            ("utm_medium", "link"),
            ("utm_campaign", redirect.slug),
        ]
    )
    url = urlunparse(parsed._replace(query=urlencode(params)))
    return django_redirect(to=url, permanent=redirect.permanent)


@login_required
def redirect_qr(request, slug):
    if not request.user.is_staff:
        raise PermissionDenied
    try:
        redirect = Redirect.get_by_slug(slug)
    except Redirect.DoesNotExist:
        raise Http404
    img_str = base64.b64encode(make_qr(redirect.full_url()))
    return render(request, "pages/qr.html", {"img": img_str.decode("utf-8"), "obj": redirect})


def proxied_site_page(request, page: str | None = None):
    one_hour = 60 * 60
    one_week = 60 * 60 * 24 * 7
    key = f"proxied_site:{page or 'home'}"
    fresh_key = f"{key}:fresh"
    should_refresh = request.GET.get("refresh", False)
    if should_refresh:
        cache.delete(fresh_key)

    # If fresh marker exists, serve cached content without refetching
    content = cache.get(key)
    if cache.get(fresh_key) and content is not None:
        return HttpResponse(content, content_type="text/html")

    # Stale or missing - try to fetch new content
    try:
        content = get_proxied_site_page(page)
        cache.set(key, content, one_week)  # Content stored for 1 week
        cache.set(fresh_key, True, one_hour)  # Fresh marker for 1 hour
        return HttpResponse(content, content_type="text/html")
    except ProxiedSiteUnavailable:
        # Fetch failed - serve stale content if available
        if content is not None:
            return HttpResponse(content, content_type="text/html")
        # No content at all - return error page
        return HttpResponse(
            "<html><body><h1>Page temporarily unavailable</h1><p>Please try again in a moment.</p></body></html>",
            content_type="text/html",
            status=503,
        )


@login_required
def dev_proxied_site_page(request, page=None):
    if not request.user.is_staff:
        raise PermissionDenied
    return proxied_site_page(request, page)


def proxied_site_proxy(request):
    return proxied_site_page(request, page=request.path_info[1:])
