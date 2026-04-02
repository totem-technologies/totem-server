from django import template
from django.utils.safestring import mark_safe

from ..models import Image

register = template.Library()


def image_template(url, alt=None):
    return f"""
<img src="{url}" alt="{alt}" class="center m-auto rounded-xl shadow-md" >
"""


@register.simple_tag(takes_context=True)
def image(context, slug):
    """get image url from an uploaded image, using prefetched cache when available"""
    cache = context.get("_image_cache")
    try:
        if cache is not None:
            img = cache.get(slug)
        else:
            img = Image.objects.get(slug=slug)
        if img and img.image:
            return mark_safe(image_template(img.image.url, alt=img.title))
    except Image.DoesNotExist:
        pass
    return
