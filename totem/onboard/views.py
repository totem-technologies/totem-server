import datetime

from django.contrib.auth.decorators import login_required
from django.forms import CharField, Form, IntegerField, Textarea, TextInput
from django.http import HttpRequest
from django.shortcuts import redirect, render

from totem.users import analytics
from totem.users.models import User
from totem.utils.slack import notify_slack
from totem.utils.utils import full_url

from .models import OnboardModel


def current_year() -> int:
    return datetime.date.today().year


class OnboardForm(Form):
    name = CharField(
        max_length=100,
        required=True,
        label="Name",
        widget=TextInput(attrs={"placeholder": "First name (or nickname)"}),
    )
    age = IntegerField(required=True, initial=None, min_value=13, max_value=120, widget=TextInput())
    hopes = CharField(max_length=1000, required=False, widget=Textarea(attrs={"rows": 3}))

    def save(self, user: User, onboard: OnboardModel):
        user.name = self.cleaned_data.pop("name")
        user.clean()
        user.save()
        onboard.year_born = current_year() - int(self.cleaned_data.pop("age"))
        for key, value in self.cleaned_data.items():
            if hasattr(onboard, key):
                setattr(onboard, key, value)
        onboard.onboarded = True
        onboard.save()
        analytics.user_onboarded(user)
        _notify_slack(user.name, full_url(user.get_admin_url()))


@login_required
def onboard_view(request: HttpRequest):
    user: User = request.user  # type: ignore
    onboard = OnboardModel.objects.get_or_create(user=user)[0]
    if request.method == "POST":
        form = OnboardForm(request.POST)
        if form.is_valid():
            form.save(user, onboard)
            return redirect("users:redirect")
    else:
        age = current_year() - onboard.year_born if onboard.year_born else None
        initial = onboard.__dict__ | {"name": user.name, "age": age}
        form = OnboardForm(initial=initial)
    return render(
        request,
        "onboard/onboard_form.html",
        {
            "form": form,
        },
    )


def _notify_slack(user_name: str, url: str):
    message = f"Onboarding: ✨*{user_name} just onboarded!*✨\n"
    message += f"Say 'Hi ✌️' at: {url}"
    notify_slack(message)
