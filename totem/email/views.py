from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.generic import TemplateView

from .emails import render_email, templates
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
        return render(request, "email/templates.html", {"templates": templates.keys()})
    return HttpResponse(render_email(name, {}))
