from django.http import Http404
from django.shortcuts import render
from django.views.generic import TemplateView

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


def signature_view(request):
    image_root = request.build_absolute_uri("/static/images/email/")
    name = request.GET.get("name", "YOUR_NAME_HERE")
    title = request.GET.get("title", "YOUR_TITLE_HERE")
    phone = request.GET.get("phone", "YOUR_PHONE_HERE")
    email = request.GET.get("email", "YOUR_EMAIL_HERE")
    return render(
        request,
        "email/signature.html",
        {"image_root": image_root, "name": name, "title": title, "phone": phone, "email": email},
    )
