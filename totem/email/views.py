from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

from totem.circles.models import Session
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
    def login_pin():
        return emails.login_pin_email(
            email="test@totem.org",
            pin="223412",
        )

    # def change_email():
    #     return emails.change_email(
    #         old_email="bo@totem.org",
    #         new_email="bo@totem.org",
    #         login_url="https://totem.org",
    #     )

    def session_starting():
        user = User.objects.first()
        session = Session.objects.last()
        if session is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_session_starting(session, user)

    def session_advertisement():
        user = User.objects.first()
        session = Session.objects.last()
        if session is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_session_advertisement(session, user)

    def session_tomorrow_reminder():
        user = User.objects.first()
        session = Session.objects.last()
        if session is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_session_tomorrow(session, user)

    def session_signup():
        user = User.objects.first()
        session = Session.objects.last()
        if session is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.notify_session_signup(session, user)

    def test():
        return emails.TestEmail(
            recipient="bo@totem.org",
            link=emails.type_url("https://totem.org"),
            start="2021-01-01",
            event_title="Test Event",
        )

    def missed_session():
        user = User.objects.first()
        session = Session.objects.last()
        if session is None or user is None:
            raise Exception("Need user or event in DB")
        return emails.missed_session_email(session, user)

    return {
        "login_pin": login_pin,  # Updated key
        # "change_email": change_email,
        "session_starting": session_starting,
        "session_advertisement": session_advertisement,
        "session_tomorrow_reminder": session_tomorrow_reminder,
        "session_signup": session_signup,
        "test": test,
        "missed_session": missed_session,
    }
