from django.core.validators import MaxLengthValidator
from django.db.models import TextField


class MaxLengthTextField(TextField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = kwargs.get("max_length", 10000)
        kwargs["validators"] = kwargs.get("validators", [MaxLengthValidator(kwargs["max_length"])])
        super().__init__(*args, **kwargs)
