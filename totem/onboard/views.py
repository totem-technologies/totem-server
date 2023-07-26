from dataclasses import dataclass

import requests
from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.forms import BooleanField, CharField, Form, HiddenInput, Textarea, TextInput
from django.shortcuts import redirect
from django.views.generic import TemplateView

from totem.utils.slack import notify_slack

from .models import OnboardModel


@dataclass
class _Circle:
    name: str
    icon: str
    description: str


class _CircleField(BooleanField):
    def __init__(self, circle: _Circle, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.circle = circle
        self.label = circle.name
        self.icon = circle.icon
        self.help_text = circle.description


class OnboardCircleForm(Form):
    circle_lgbtq = _CircleField(
        required=False,
        circle=_Circle(
            "LGBTQ+",
            "🏳️‍🌈",
            "This Circle is about creating a safe and affirming space for the LGBTQ+ community to share the unique experiences, discuss challenges, and celebrate our identities.",
        ),
    )
    circle_mothers = _CircleField(
        required=False,
        circle=_Circle(
            "Parenthood",
            "🐣",
            "This Circle is about providing a nurturing environment for parents to share the experiences, triumphs, and difficulties of rasing children.",
        ),
    )
    circle_sexuality = _CircleField(
        required=False,
        circle=_Circle(
            "Sexuality",
            "❤️‍🔥",
            "This Circle is about providing an open and safe environment for us to discuss and explore the topics of sexuality and kink.",
        ),
    )
    circle_psych = _CircleField(
        required=False,
        circle=_Circle(
            "Psychedelics",
            "🍄",
            "This Circle is about offering a non-judgmental space to discuss personal experiences, thoughts, and insights relating to psychedelics. This is also called an Integration Circle.",
        ),
    )
    circle_general = _CircleField(
        required=False,
        circle=_Circle(
            "General",
            "🗺️",
            "The General Circle is designed to explore our shared human connection. We create these Circles with as much diversity as possible to maximize our learning of each other.",
        ),
    )


class OnboardNameForm(Form):
    name = CharField(
        max_length=100,
        required=True,
        label="Name",
        widget=TextInput(attrs={"placeholder": "Josie (They/Them)"}),
    )


class OnboardExtraForm(Form):
    suggestions = CharField(max_length=1000, required=False, widget=Textarea(attrs={"rows": 3}))
    timezone = CharField(max_length=255, required=False, widget=HiddenInput())


class OnboardView(LoginRequiredMixin, TemplateView):
    template_name = "onboard/onboard_form.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["name_form"] = OnboardNameForm(initial={"name": self.request.user.name})  # type: ignore
        onboard = self.get_onboard_model()
        context["circle_form"] = OnboardCircleForm(initial=onboard.__dict__)
        context["extra_form"] = OnboardExtraForm(initial=onboard.__dict__)
        return context

    def get_onboard_model(self):
        return OnboardModel.objects.get_or_create(user=self.request.user)[0]

    def get_success_url(self) -> str:
        return self.request.user.get_absolute_url()  # type: ignore

    def post(self, request, *args, **kwargs):
        name_form = OnboardNameForm(request.POST)
        circle_form = OnboardCircleForm(request.POST)
        extra_form = OnboardExtraForm(request.POST)
        if name_form.is_valid() and circle_form.is_valid() and extra_form.is_valid():
            self.request.user.name = name_form.cleaned_data.pop("name")
            self.request.user.save()
            onboard = self.get_onboard_model()
            interests = []
            for key, value in circle_form.cleaned_data.items():
                setattr(onboard, key, value)
                if value:
                    interests.append(key)
            for key, value in extra_form.cleaned_data.items():
                setattr(onboard, key, value)
            onboard.onboarded = True
            onboard.save()
            admin_url = request.build_absolute_uri(request.user.get_admin_url())
            _notify_slack(self.request.user.name, admin_url, interests)
            return redirect(self.get_success_url())
        else:
            return self.get(request, *args, **kwargs)


def _notify_slack(user_name: str, url: str, interests: list[str]):
    message = f"Onboarding: ✨*{user_name} just onboarded!*✨\n They are interested in:\n"
    for interest in interests:
        message += f" · {interest}\n"
    message += f"Say 'Hi ✌️' at: {url}"
    notify_slack(message)
