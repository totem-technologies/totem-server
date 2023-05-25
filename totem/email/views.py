from django.http import Http404
from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView

from .models import WaitList


class WaitListAddView(CreateView):
    model = WaitList
    fields = ["name", "email"]
    success_url = reverse_lazy("email:waitlist_sent")

    def form_valid(self, form):
        self.object = form.save()
        self.object.send_subscribe_email()
        return super().form_valid(form)


class WaitListSubscribeView(TemplateView):
    template_name = "email/waitlist_subscribe.html"

    def get(self, request, *args, **kwargs):
        try:
            waitlist = WaitList.objects.get(id=kwargs["id"])
            waitlist.subscribe()
        except WaitList.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)
