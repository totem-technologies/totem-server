from django.conf import settings
from django.db import models


# Create your models here.
class OnboardModel(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="onboard",
    )
    onboarded = models.BooleanField(default=False)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    circle_lgbtq = models.BooleanField(default=False)
    circle_mothers = models.BooleanField(default=False)
    circle_sexuality = models.BooleanField(default=False)
    circle_psych = models.BooleanField(default=False)
    circle_general = models.BooleanField(default=False)
    suggestions = models.TextField(blank=True, null=True)
    internal_notes = models.TextField(blank=True, null=True)
    timezone = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"Onboard: {self.user}"
