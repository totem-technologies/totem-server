from django.db import models
from django.conf import settings

class CirclePlan(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    content = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    def __str__(self):
        return self.name