from django.conf import settings
from django.db import models
from taggit.managers import TaggableManager


class Prompt(models.Model):
    prompt = models.CharField(max_length=1000)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True, null=True)
    tags = TaggableManager()

    @property
    def tag_list(self):
        return ", ".join([n.name for n in self.tags.all()])

    def __str__(self):
        return self.prompt
