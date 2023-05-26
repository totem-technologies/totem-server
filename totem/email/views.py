from django.forms import ModelForm
from django.http import Http404
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView

from .models import WaitList


class WaitListForm(ModelForm):
    class Meta:
        model = WaitList
        fields = ["name", "email"]


class WaitListAddView(FormView):
    form_class = WaitListForm
    fields = ["name", "email"]
    success_url = reverse_lazy("email:waitlist_survey")
    template_name = "email/waitlist_form.html"

    def validate_unique(self):
        pass

    def form_valid(self, form):
        try:
            self.object = WaitList.objects.get(email=form.cleaned_data["email"])
            print("found existing waitlist")
        except WaitList.DoesNotExist:
            print("noexist")
            self.object = form.save()
        print("bleepbloop")
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
