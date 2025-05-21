from django.conf import settings
from django.core.validators import MaxLengthValidator
from django.db import models


class ReferralChoices(models.TextChoices):
    DEFAULT = "default", "I'm not sure"
    SEARCH = "search", "Search Results"
    SOCIAL = "social", "Social Media"
    KEEPER = "keeper", "A Keeper"
    PAMPHLET = "pamphlet", "Pamphlet"
    BLOG = "blog", "Blog"
    NEWSLETTER = "newsletter", "Newsletter"
    DREAM = "dream", "✨A Dream✨"
    OTHER = "other", "Other"


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
    suggestions = models.TextField(blank=True, null=True, validators=[MaxLengthValidator(5000)])
    hopes = models.TextField(blank=True, null=True, validators=[MaxLengthValidator(5000)])
    internal_notes = models.TextField(blank=True, null=True, validators=[MaxLengthValidator(10000)])
    referral_source = models.CharField(
        max_length=20,
        choices=ReferralChoices.choices,
        default="default",
        verbose_name="How did you hear about us?",
        blank=True,  # Remove if you want to make it required
    )
    referral_other = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="If other, please specify",
        help_text="Please tell us more about how you found us",
    )

    def __str__(self):
        return f"Onboard: {self.user}"

    @property
    def user_name(self):
        return self.user.name
