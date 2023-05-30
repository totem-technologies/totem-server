from django import forms
from django.forms import ModelForm
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import FormView, TemplateView, View

from .models import WaitList


class WaitListForm(forms.Form):
    email = forms.EmailField(label="Your email", required=True)
    name = forms.CharField(label="Your name", required=True)


class WaitListAddView(View):
    form_class = WaitListForm
    success_url = reverse_lazy("email:waitlist_survey")
    template_name = "email/waitlist_form.html"

    def get(self, request, *args, **kwargs):
        form = self.form_class()
        return render(request, self.template_name, {"form": form})

    def post(self, request, *args, **kwargs):
        form = self.form_class(request.POST)
        form.full_clean()
        if form.is_valid():
            try:
                instance = WaitList.objects.get(email=form.cleaned_data["email"])
            except WaitList.DoesNotExist:
                print("noexist")
                instance = WaitList.objects.create(**form.cleaned_data)
                instance.save()
            instance.send_subscribe_email()
            return redirect(self.success_url)
        else:
            return render(request, self.template_name, {"form": form})


class WaitListSubscribeView(TemplateView):
    template_name = "email/subscribe.html"

    def get(self, request, *args, **kwargs):
        try:
            waitlist = WaitList.objects.get(id=kwargs["id"])
            waitlist.subscribe()
        except WaitList.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)


class WaitListUnsubscribeView(TemplateView):
    template_name = "email/unsubscribe.html"

    def get(self, request, *args, **kwargs):
        try:
            waitlist = WaitList.objects.get(id=kwargs["id"])
            waitlist.unsubscribe()
        except WaitList.DoesNotExist:
            raise Http404
        return super().get(request, *args, **kwargs)
