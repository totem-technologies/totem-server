import markdown as md
from django import template
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def markdown(file_path):
    # Find the markdown file using Django's template loader
    try:
        source = render_to_string(file_path)
    except TemplateDoesNotExist:
        raise TemplateDoesNotExist(f"Markdown file '{file_path}' not found.")

    # Convert markdown content to HTML
    html = md.markdown(source)
    return mark_safe(html)
