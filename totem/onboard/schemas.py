from .models import OnboardModel
from ninja import ModelSchema
from enum import Enum


ReferralSource = Enum("ReferralSource", {a[0]: a[0] for a in OnboardModel.REFERRAL_CHOICES})


class OnboardSchema(ModelSchema):
    # @staticmethod
    # def resolve_referral_source(obj):
    #     if obj.referral_source:
    #         return obj.referral_source.value
    #     return None

    class Meta:
        model = OnboardModel
        fields = ["year_born", "hopes", "referral_other", "referral_source"]
        # fields_optional = ["hopes", "referral_other", "referral_source"]
