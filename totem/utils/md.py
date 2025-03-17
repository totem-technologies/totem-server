import markdown
from django import forms
from django.contrib.admin import widgets as admin_widgets
from django.core.exceptions import ValidationError
from django.core.validators import MaxLengthValidator
from django.db.models import TextField
from django.forms import widgets
from django.template import Context, Template
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe


class _MarkdownWidget(widgets.Textarea):
    def __init__(self, *args, **kwargs):
        self.custom_options = kwargs.pop("markdown_options", {})
        super().__init__(*args, **kwargs)

    def render(self, name, value, attrs: dict | None = None, renderer=None):
        attrs = attrs or {}

        if "class" not in attrs:
            attrs["class"] = ""

        attrs["class"] += " markdown-widget"
        attrs["height"] = "400px"

        html = super().render(name, value, attrs, renderer=renderer)

        # insert this style tag to fix the label from breaking into the toolbar
        html += "<style>.field-%s label { float: none; }</style>" % name

        return mark_safe(html)

    def _media(self):
        js = ("js/markdown.min.js", "js/markdown.init.js")
        css = {"all": ("css/markdown.min.css",)}
        return forms.Media(css=css, js=js)  # type: ignore

    media = property(_media)


class MarkdownMixin:
    @classmethod
    def validate_markdown(cls, value):
        # Check for prohibited H1 headers
        if any(line.strip().startswith("# ") for line in value.split("\n")):
            raise ValidationError("H1 headers (starting with #) are not allowed in content")

        try:
            # Verify markdown can be rendered
            cls.render_markdown(value)
        except Exception as e:
            raise ValidationError(f"Markdown error: {str(e)}") from e

    @staticmethod
    def render_markdown(content: str):
        if not content:
            return ""
        templatetags = "\n".join(["{% load image %}"]) + "\n"
        content = content or ""
        md = markdown.Markdown(extensions=["toc"]).convert(content)
        return Template(templatetags + md).render(Context())

    @property
    def content_html(self):
        return self.render_markdown(getattr(self, "content", ""))

    @property
    def content_text(self):
        return strip_tags(self.render_markdown(getattr(self, "content", "")))

    @property
    def toc(self):
        md = markdown.Markdown(extensions=["toc"])
        _ = md.convert(getattr(self, "content", ""))
        toc = md.toc  # type: ignore
        return toc


class MarkdownField(TextField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = kwargs.get("max_length", 10000)
        kwargs["validators"] = kwargs.get(
            "validators", [MarkdownMixin.validate_markdown, MaxLengthValidator(kwargs["max_length"])]
        )
        self.widget = _MarkdownWidget()
        super().__init__(*args, **kwargs)

    def formfield(self, **kwargs):
        defaults = {"widget": self.widget}
        defaults.update(kwargs)

        if defaults["widget"] == admin_widgets.AdminTextareaWidget:
            defaults["widget"] = self.widget
        return super().formfield(**defaults)

    def clean(self, value: str, model_instance):
        value = super().clean(value, model_instance)
        if value is None:
            return value
        value = value.replace("\r\n", "\n")
        value = value.replace("\n\n\n", "\n")
        lines = value.split("\n")
        lines = [line.rstrip() for line in lines]
        value = "\n".join(lines)
        return value
