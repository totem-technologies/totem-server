from django.conf import settings
from django.db import models


class OnboardModel(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboard",
    )
    onboarded = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    year_born = models.IntegerField(blank=True, null=True, choices=[(i, str(i)) for i in range(1900, 2200)])
    suggestions = models.TextField(blank=True, null=True)
    hopes = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Onboard: {self.user}"

    @property
    def user_name(self):
        return self.user.name
