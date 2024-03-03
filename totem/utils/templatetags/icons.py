from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag()
def icons(icon_name: str, size=None):
    """Return an icon in SVG format from a template tag."""
    context = {
        "width": size,
        "height": size,
    }
    # Attempt to load the template by the given icon name
    svg_content = render_to_string(f"icons/{icon_name}.html", context=context)
    return mark_safe(svg_content)  # mark_safe tells Django not to escape the SVG HTML
