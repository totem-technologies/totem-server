from django.contrib.auth import get_user_model
from django.forms import CharField, EmailField, Form


class ParticipateLoginForm(Form):
    name = CharField(label="Preferred name")
    email = EmailField()


class ParticipateOnboardForm(Form):
    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def save(self):
        self.user.profile.onboarded = True
        self.user.profile.save()
