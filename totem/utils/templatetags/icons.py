import functools

import lxml.etree
from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag()
def icons(icon_name: str, size=24):
    """Return an icon in SVG format from a template tag."""
    # Attempt to load the template by the given icon name
    svg_content = _read_svg_file(icon_name, size)
    return mark_safe(svg_content)  # mark_safe tells Django not to escape the SVG HTML


@functools.lru_cache(maxsize=1000)
def _read_svg_file(icon_name: str, size: int) -> str:
    """Read an SVG file using Django's template loader"""
    svg_content = render_to_string(f"icons/{icon_name}.svg")
    parser = lxml.etree.XMLParser(remove_blank_text=True)
    svg = lxml.etree.fromstring(svg_content, parser)

    # Set the width and height attributes
    svg.attrib["width"] = svg.attrib["height"] = str(size)

    # Remove the xmlns attribute from the root element
    return lxml.etree.tostring(svg).decode("utf-8").replace('xmlns="http://www.w3.org/2000/svg"', "")
