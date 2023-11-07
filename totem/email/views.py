from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

from .models import SubscribedModel
from .utils import get_templates, render_email


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
    sample_data = {
        "first_name": "John",
        "last_name": "Doe",
        "email": "",
        "link": "https://www.google.com",
        "subject": "Test Subject",
        "message": "Test Message",
        "button_text": "Test Button Text",
        "title": "Test Title",
    }
    return render(request, "email/email_viewer.html", context={"email": render_email(name, sample_data)})
