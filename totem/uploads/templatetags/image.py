from django import template
from django.utils.safestring import mark_safe

from ..models import Image

register = template.Library()


def image_template(url, alt=None):
    return f"""
<img src="{url}" alt="{alt}" class="center m-auto rounded-xl shadow-md" >
"""


@register.simple_tag
def image(slug):
    """get image url from an uploaded image"""
    try:
        image = Image.objects.get(slug=slug)
        if image.image:
            return mark_safe(image_template(image.image.url, alt=image.title))
    except Image.DoesNotExist:
        pass
    return
