import markdown
from django.conf import settings
from django.db import models
from django.urls import reverse

from totem.utils.fields import MarkdownField


class MardownMixin:
    @property
    def content_html(self):
        md = markdown.Markdown(extensions=["toc"])
        return md.convert(getattr(self, "content", ""))

    @property
    def toc(self):
        md = markdown.Markdown(extensions=["toc"])
        _ = md.convert(getattr(self, "content", ""))
        toc = md.toc
        return toc


class Course(MardownMixin, models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    content = MarkdownField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("course:list")


class CircleScript(MardownMixin, models.Model):
    title = models.CharField(max_length=255)
    content = MarkdownField()
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("course:script")
