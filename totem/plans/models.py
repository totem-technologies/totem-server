from django.urls import reverse
from django.utils import timezone
from django.db import models
from django.conf import settings
from django.template.defaultfilters import truncatechars
import markdown


class CirclePlan(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    content = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    display_date = models.DateTimeField(default=timezone.now)
    published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    @property
    def short_description(self):
        return truncatechars(self.description, 35)

    @property
    def content_html(self):
        return markdown.markdown(self.content)

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("plans:detail", kwargs={"pk": self.pk})
