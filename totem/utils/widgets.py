import uuid
from typing import Any, Dict, List, Optional, Union

from django import forms
from django.conf import settings
from django.forms import widgets
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe


class MarkdownWidget(widgets.Textarea):
    def __init__(self, *args, **kwargs):
        self.custom_options = kwargs.pop("markdown_options", {})
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs: dict | None = None, renderer=None):
        attrs = attrs or {}

        if "class" not in attrs:
            attrs["class"] = ""

        attrs["class"] += " markdown-widget"

        html = super().render(name, value, attrs, renderer=renderer)

        # insert this style tag to fix the label from breaking into the toolbar
        html += "<style>.field-%s label { float: none; }</style>" % name

        return mark_safe(html)

    def _media(self):
        js = ("js/markdown.min.js", "js/markdown.init.js")
        css = {"all": ("css/markdown.min.css",)}
        return forms.Media(css=css, js=js)

    media = property(_media)
