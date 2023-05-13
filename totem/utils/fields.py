from django.conf import settings
from django.contrib.admin import widgets as admin_widgets
from django.db.models import TextField

from .widgets import MarkdownWidget


class MarkdownField(TextField):
    def __init__(self, *args, **kwargs):
        self.widget = MarkdownWidget()
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        defaults = {"widget": self.widget}
        defaults.update(kwargs)

        if defaults["widget"] == admin_widgets.AdminTextareaWidget:
            defaults["widget"] = self.widget
        return super().formfield(**defaults)
