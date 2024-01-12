from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

from .emails import ChangeEmailEmail, CircleAdvertisementEmail, CircleStartingEmail, LoginEmail
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
    if name is None:
        return render(request, "email/templates.html", {"templates": get_templates().keys()})
    templates = get_templates()
    if name not in templates:
        raise Http404
    email = templates[name]
    return render(
        request,
        "email/email_viewer.html",
        context={"html": email.get_template().render_html(), "text": email.get_template().render_text()},
    )


def get_templates():
    # files = Path(__file__).parent.joinpath("templates/email/emails").glob("*.mjml")
    # return {file.stem: file.name for file in files}
    return {
        "login_email": LoginEmail(
            recipient="bo@totem.org",
            url="https://totem.org",  # type: ignore
        ),
        "change_email": ChangeEmailEmail(
            recipient="bo@totem.org",
            old_email="b2@totem.org",
            new_email="bo@totem.org",
            login_url="https://totem.org",  # type: ignore
        ),
        "circle_starting": CircleStartingEmail(
            recipient="bo@totem.org",
            start="2021-01-01",
            event_title="Test Event",
            link="https://totem.org",  # type: ignore
        ),
        "circle_advertisement": CircleAdvertisementEmail(
            recipient="bo@totem.org",
            link="https://totem.org",  # type: ignore
            start="2021-01-01",
            event_title="Test Event",
            unsubscribe_url="https://totem.org?bo=bo&cool=cool",  # type: ignore
        ),
    }
