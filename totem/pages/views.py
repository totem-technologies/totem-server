import base64
import random
import uuid
from dataclasses import dataclass
from typing import Optional

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.shortcuts import redirect as django_redirect
from django.shortcuts import render
from django.urls import reverse
from django.views.generic import TemplateView

from ..users.models import User
from .models import Redirect
from .qrmaker import make_qr
from .webflow import get_webflow_page


@dataclass
class Member:
    name: str
    title: str
    image: str
    url: Optional[str]
    external: bool

    def imageurl(self):
        return f"images/team/{self.image}"


def team_view(request):
    team = [
        Member(
            name="Bo Lopker",
            title="Executive Director, Keeper, Co-Founder",
            image="bo.jpg",
            url=reverse("pages:keepers", kwargs={"name": "bo"}),
            external=False,
        ),
        Member(name="Pam Lopker", title="Board Member", image="pam.jpg", url=reverse("pages:team-pam"), external=False),
        Member(
            name="Gabe Kenny",
            title="User Research, Keeper, Co-Founder",
            image="gabe.jpg",
            url=reverse("pages:keepers", kwargs={"name": "gabe"}),
            external=False,
        ),
        Member(
            name="Claire Hopkins",
            title="Keeper",
            image="claire.webp",
            url=reverse("pages:keepers", kwargs={"name": "claire"}),
            external=False,
        ),
        Member(
            name="Adil Sakout", title="Engineer", image="adil.webp", url="https://www.adilsakout.com/", external=True
        ),
        Member(
            name="Bruno D'Luka", title="Engineer", image="bruno.webp", url="https://github.com/bdlukaa", external=True
        ),
        Member(
            name="Heather Gressett",
            title="Content Curator, Keeper, Co-Founder",
            image="heather.jpg",
            url=reverse("pages:keepers", kwargs={"name": "heather"}),
            external=False,
        ),
        Member(
            name="Vanessa Robinson",
            title="Webmaster, Keeper, Co-Founder",
            image="vanessa.jpg",
            url=reverse("pages:keepers", kwargs={"name": "vanessa"}),
            external=False,
        ),
        Member(
            name="Bob Lesser, MPP, LP",
            title="Psychotherapist Advisor",
            image="boblesser.webp",
            url="https://boblesser.com/",
            external=True,
        ),
        Member(
            name="Steve Schalkhauser",
            title="Engineer, Phase 2",
            image="blank.jpg",
            url="https://phase2industries.com/",
            external=True,
        ),
        Member(
            name="Steve Ansell",
            title="Engineer, Phase 2",
            image="blank.jpg",
            url="https://phase2industries.com/",
            external=True,
        ),
        Member(
            name="Smita Agarwal",
            title="Advisor",
            image="smita.jpg",
            url="https://www.linkedin.com/in/smita-agarwal-4012164/",
            external=True,
        ),
        Member(
            name="Jesse Woche",
            title="Keeper",
            image="jesse.webp",
            url=reverse("pages:keepers", kwargs={"name": "jesse"}),
            external=False,
        ),
    ]
    # randomly shuffle the team
    random.seed(str(uuid.uuid4()))
    random.shuffle(team)
    template_name = "pages/team.html"
    context = {"team": team, "keepers": keepers}
    return render(request, template_name, context=context)


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
    return django_redirect(to=redirect.url, permanent=redirect.permanent)


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


def webflow_page(request, page: str | None = None):
    from totem.pages.webflow import WebflowUnavailable

    one_hour = 60 * 60
    one_week = 60 * 60 * 24 * 7
    key = f"webflow:{page or 'home'}"
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
        content = get_webflow_page(page)
        cache.set(key, content, one_week)  # Content stored for 1 week
        cache.set(fresh_key, True, one_hour)  # Fresh marker for 1 hour
        return HttpResponse(content, content_type="text/html")
    except WebflowUnavailable:
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
def dev_webflow_page(request, page=None):
    if not request.user.is_staff:
        raise PermissionDenied
    return webflow_page(request, page)


def webflow_proxy(request):
    return webflow_page(request, page=request.path_info[1:])
