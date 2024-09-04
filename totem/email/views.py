from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

from totem.utils.md import MarkdownMixin

from .emails import (
    ChangeEmailEmail,
    CircleAdvertisementEmail,
    CircleSignupEmail,
    CircleStartingEmail,
    CircleTomorrowReminderEmail,
    LoginEmail,
    MissedEventEmail,
    TestEmail,
    type_url,
)
from .models import SubscribedModel


class SubscribeView(TemplateView):
    template_name = "email/subscribe.html"

    def get(self, request, *args, **kwargs):
        try:
            waitlist = SubscribedModel.objects.get(id=kwargs["id"])
            waitlist.subscribe()
        except SubscribedModel.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)


class UnsubscribeView(TemplateView):
    template_name = "email/unsubscribe.html"

    def get(self, request, *args, **kwargs):
        try:
            waitlist = SubscribedModel.objects.get(id=kwargs["id"])
            waitlist.unsubscribe()
        except SubscribedModel.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)


def template_view(request, name=None):
    if not settings.DEBUG and not request.user.is_staff:
        raise Http404
    if name is None:
        return render(request, "email/templates.html", {"templates": get_templates().keys()})
    templates = get_templates()
    if name not in templates:
        raise Http404
    email = templates[name]
    return render(
        request,
        "email/email_viewer.html",
        context={"html": email.render_html(), "text": email.render_text()},
    )


event_details = """
## Sexual Liberation

Sexual liberation is going to look different for each of us. For some, it may actually mean less sex—liberating your voice to say 'no' to your partner more often. For others, sexual liberation might involve buying your first solo toy or exploring a threesome. We are all on different journeys, and this space is dedicated to destigmatizing conversations about sex in a safe environment, identifying our personal boundaries, and discovering what sexual liberation means to each of us.

We will ask questions like:

* *What would sexual liberation look like in your life, and why would that be important?*

We hope that after this space, you feel emboldened in your desires and in your ability to voice them."""


def get_templates():
    # files = Path(__file__).parent.joinpath("templates/email/emails").glob("*.mjml")
    # return {file.stem: file.name for file in files}
    return {
        "login_email": LoginEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
        ),
        "change_email": ChangeEmailEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
        ),
        "circle_starting": CircleStartingEmail(
            recipient="bo@totem.org",
            start="2021-01-01",
            event_title="Test Event",
            event_link=type_url("https://totem.org/event"),
            link=type_url("https://totem.org"),
        ),
        "circle_advertisement": CircleAdvertisementEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
            start="2021-01-01",
            event_title="What is Love? A Queer Loveletter",
            space_title="LGBTQIA+ Queer Space",
            author="John Doe",
            space_subtitle="A Queer Space",
            unsubscribe_url=type_url("https://totem.org?bo=bo&cool=cool"),
            title="What is Love? A Queer Loveletter",
            subtitle="A Queer Space",
            image_url="https://org-totem-media.sfo3.cdn.digitaloceanspaces.com/circles/gmq438ijs/0172da11960cd18f2371.jpg",
            # image_url=None,
            author_image_url="https://org-totem-media.sfo3.cdn.digitaloceanspaces.com/profiles/gmq438ijs/4dc0bac00f3a4968e007.jpg",
            event_details=MarkdownMixin.render_markdown(event_details),
            # event_details="",
        ),
        "circle_tomorrow_reminder": CircleTomorrowReminderEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
            start="2021-01-01",
            event_title="Test Event",
        ),
        "circle_signup": CircleSignupEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
            start="2021-01-01",
            event_title="Test Event",
        ),
        "test": TestEmail(
            recipient="bo@totem.org",
            link=type_url("https://totem.org"),
            start="2021-01-01",
            event_title="Test Event",
        ),
        "missed_event": MissedEventEmail(
            recipient="bo@totem.org",
            start="2021-01-01",
            event_title="Test Event",
            event_link=type_url("https://totem.org"),
        ),
    }
