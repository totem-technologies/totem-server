from django import template
from django.urls import reverse

register = template.Library()


@register.simple_tag(takes_context=True)
def absurl(context, view_name, *args, **kwargs):
    # Could add except for KeyError, if rendering the template
    # without a request available.
    return (
        context["request"]
        .build_absolute_uri(reverse(view_name, args=args, kwargs=kwargs))
        .replace("http://", "https://")
    )


@register.filter
def as_absurl(path, request):
    return request.build_absolute_uri(path)
