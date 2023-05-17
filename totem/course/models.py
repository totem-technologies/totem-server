import markdown
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.template import Context, Template
from django.urls import reverse

from totem.utils.fields import MarkdownField


class MardownMixin:
    @staticmethod
    def validate_markdown(value):
        try:
            MardownMixin.render_markdown(value)
        except Exception as e:
            raise ValidationError(e)

    @staticmethod
    def render_markdown(content: str):
        md = markdown.Markdown(extensions=["toc"])
        return Template(md.convert(content)).render(Context())

    @property
    def content_html(self):
        return self.render_markdown(getattr(self, "content", ""))

    @property
    def toc(self):
        md = markdown.Markdown(extensions=["toc"])
        _ = md.convert(getattr(self, "content", ""))
        toc = md.toc
        return toc


class CoursePage(MardownMixin, models.Model):
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    enable_toc = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    content = MarkdownField(validators=[MardownMixin.validate_markdown])
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.title} - {self.slug}"

    def get_absolute_url(self):
        return reverse("course:page", kwargs={"slug": self.slug})
