import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(is_safe=True)
def jsonld(value):
    """
    Output value JSON-encoded, wrapped in a <script type="application/ld+json">
    tag.
    """
    return _json_script(value)


_json_script_escapes = {
    ord(">"): "\\u003E",
    ord("<"): "\\u003C",
    ord("&"): "\\u0026",
}


def _json_script(value):
    """
    Escape all the HTML/XML special characters with their unicode escapes, so
    value is safe to be output anywhere except for inside a tag attribute. Wrap
    the escaped JSONLD in a script tag.
    """
    from django.core.serializers.json import DjangoJSONEncoder

    json_str = json.dumps(value, cls=DjangoJSONEncoder).translate(_json_script_escapes)
    template = '<script type="application/ld+json">{}</script>'
    args = (mark_safe(json_str),)
    return format_html(template, *args)
