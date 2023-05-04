from django.db import models
from django.conf import settings
from django.urls import reverse
import markdown


class Course(models.Model):
    title = models.CharField(max_length=255)
    description = models.TextField()
    content = models.TextField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    @property
    def content_html(self):
        return markdown.markdown(self.content)

    def get_absolute_url(self):
        return reverse("course:list")
