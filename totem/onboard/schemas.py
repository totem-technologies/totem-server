from .models import OnboardModel, ReferralChoices
from ninja import ModelSchema


class OnboardSchema(ModelSchema):
    referral_source: ReferralChoices = ReferralChoices.DEFAULT

    class Meta:
        model = OnboardModel
        fields = ["year_born", "hopes", "referral_other"]
        # fields_optional = ["hopes", "referral_other", "referral_source"]
