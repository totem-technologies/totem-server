from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

from totem.circles.models import CircleEvent
from totem.users.models import User

from . import emails
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
    email = templates[name]()
    return render(
        request,
        "email/email_viewer.html",
        context={"html": email.render_html(), "text": email.render_text()},
    )


def get_templates():
    # files = Path(__file__).parent.joinpath("templates/email/emails").glob("*.mjml")
    # return {file.stem: file.name for file in files}
    def login_email():
        return emails.returning_login_email(
            email="bo@totem.org",
            url="https://totem.org",
        )

    def change_email():
        return emails.change_email(
            old_email="bo@totem.org",
            new_email="bo@totem.org",
            login_url="https://totem.org",
        )

    def circle_starting():
        user = User.objects.first()
        event = CircleEvent.objects.last()
        if event is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_circle_starting(event, user)

    def circle_advertisement():
        user = User.objects.first()
        event = CircleEvent.objects.last()
        if event is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_circle_advertisement(event, user)

    def circle_tomorrow_reminder():
        user = User.objects.first()
        event = CircleEvent.objects.last()
        if event is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_circle_tomorrow(event, user)

    def circle_signup():
        user = User.objects.first()
        event = CircleEvent.objects.last()
        if event is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_circle_signup(event, user)

    def test():
        return emails.TestEmail(
            recipient="bo@totem.org",
            link=emails.type_url("https://totem.org"),
            start="2021-01-01",
            event_title="Test Event",
        )

    def missed_event():
        user = User.objects.first()
        event = CircleEvent.objects.last()
        if event is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.missed_event_email(event, user)

    return {
        "login_email": login_email,
        "change_email": change_email,
        "circle_starting": circle_starting,
        "circle_advertisement": circle_advertisement,
        "circle_tomorrow_reminder": circle_tomorrow_reminder,
        "circle_signup": circle_signup,
        "test": test,
        "missed_event": missed_event,
    }
