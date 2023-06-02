from django.http import Http404
from django.views.generic import TemplateView

from .models import SubscribedModel

# class WaitListAddView(View):
#     form_class = WaitListForm
#     success_url = reverse_lazy("email:waitlist_survey")
#     template_name = "email/waitlist_form.html"

#     def get(self, request, *args, **kwargs):
#         form = self.form_class()
#         return render(request, self.template_name, {"form": form})

#     def post(self, request, *args, **kwargs):
#         form = self.form_class(request.POST)
#         form.full_clean()
#         if form.is_valid():
#             try:
#                 instance = WaitList.objects.get(email=form.cleaned_data["email"])
#             except WaitList.DoesNotExist:
#                 print("noexist")
#                 instance = WaitList.objects.create(**form.cleaned_data)
#                 instance.save()
#             instance.send_subscribe_email()
#             return redirect(self.success_url)
#         else:
#             return render(request, self.template_name, {"form": form})


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
