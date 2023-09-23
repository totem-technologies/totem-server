import base64
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect as django_redirect
from django.shortcuts import render
from django.urls import reverse_lazy
from django.views.generic import TemplateView

from ..users.forms import LoginForm
from .models import Redirect
from .qrmaker import make_qr

User = get_user_model()


@dataclass
class Member:
    name: str
    title: str
    image: str
    url: str

    def imageurl(self):
        return f"images/team/{self.image}"


class TeamView(TemplateView):
    team = [
        Member(name="Bo Lopker", title="Executive Director, Keeper", image="bo.jpg", url=reverse_lazy("pages:about")),
        Member(name="Pam Lopker", title="Board Member", image="pam.jpg", url=reverse_lazy("pages:team-pam")),
        Member(
            name="Gabe Kenny",
            title="User Research, Keeper",
            image="gabe.jpg",
            url=reverse_lazy("pages:keepers", kwargs={"name": "gabe"}),
        ),
        Member(
            name="Heather Gressett",
            title="Content Curator, Keeper",
            image="heather.jpg",
            url=reverse_lazy("pages:keepers", kwargs={"name": "heather"}),
        ),
        Member(
            name="Vanessa Robinson",
            title="Keeper",
            image="vanessa.jpg",
            url=reverse_lazy("pages:keepers", kwargs={"name": "vanessa"}),
        ),
        # Member(
        #     name="Josie Maestre",
        #     title="Keeper",
        #     image="josie.jpg",
        #     url=reverse_lazy("pages:keepers-josie"),
        # ),
        Member(
            name="Steve Schalkhauser",
            title="Engineer, Phase 2",
            image="blank.jpg",
            url="https://phase2industries.com/",
        ),
        Member(name="Steve Ansell", title="Engineer, Phase 2", image="blank.jpg", url="https://phase2industries.com/"),
    ]
    template_name = "pages/team.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["team"] = self.team
        return context


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


@dataclass
class FAQ:
    question: str
    answer: str


class HomeView(TemplateView):
    template_name = "pages/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["quotes"] = [
            "I appreciate having a space to express myself and not feel the need to validate or \
                respond to others.",
            "It was the best experience.",
            "I'm so glad I came, this is exactly what I've been needing.",
            "This is definitely a safe and welcoming environment.",
            "My expectations were exceeded 10000%.",
            "YES!!! I love the safe space that was created.",
        ]
        context["faqs"] = [
            FAQ(
                question="Can I be anonymous?",
                answer="Yes! We don't mind if you don't use your real name. We will require \
                    enough information for moderation, like your email, but to other people \
                        in your Circles (including Keepers) you can be whoever you want to \
                            be. However, we do require you share authentic stories.",
            ),
            FAQ(
                question="What about privacy?",
                answer="We have zero tolerance about discussing what happens in Totem to the \
                    outside. Anyone doing this will be permanently removed. Additionally, we \
                        built Totem on top of HIPAA-compliant services, the same software \
                            that therapists and doctors use to do online sessions. Your \
                communications are encrypted. The only people who can hear your shares are the \
                    people in your Circle.",
            ),
            FAQ(
                question="Is this a replacement for therapy?",
                answer="No. While many people prefer Totem Circles to therapy, it is not a \
                replacement for traditional one-on-one therapy. However, Totem does make a great \
                supplement if you already have ongoing therapy sessions and can help create a \
                deeper understanding with your work there.",
            ),
            FAQ(
                question="Are Keepers therapists?",
                answer="Generally, no. Keepers are different from therapists in that they are \
                only present to keep the Circle running smoothly and safely for everyone. \
                Otherwise, Keepers are there to be involved with the discussion like everyone else \
                    and not to offer advice or guidance. There is no hierarchy in a Circle.",
            ),
            FAQ(
                question="How much does Totem cost?",
                answer="It depends on the Circle, some are free, some aren't. Our mission is to \
                    make Totem Circles accessible to as many people as possible. In the future we'll \
                        add the ability to donate directly to your Keeper if you'd like to \
                            support them. ",
            ),
        ]
        context["signup_form"] = LoginForm()
        return context


def keepers(request, name):
    return render(request, f"pages/keepers/{name}.html")


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
        raise Http404
    try:
        redirect = Redirect.get_by_slug(slug)
    except Redirect.DoesNotExist:
        raise Http404
    img_str = base64.b64encode(make_qr(redirect.full_url()))
    return render(request, "pages/qr.html", {"img": img_str.decode("utf-8"), "obj": redirect})


@login_required
def training(request):
    enroll_url = "https://secure.totem.org/b/7sI03l8LD1zl5eU9AJ"
    return render(request, "pages/training.html", {"enroll_url": enroll_url})
