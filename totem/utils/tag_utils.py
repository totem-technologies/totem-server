import string

from taggit.utils import _parse_tags

_legal_chars = {
    "-",
    " ",
    ",",
    "+",
}
_legal_chars.update(string.ascii_lowercase)
_legal_chars.update(string.digits)


def parse_tags(tag_string: str):
    tag_string = tag_string.lower()
    clean_tag_string = ""
    for char in tag_string:
        if char in _legal_chars:
            clean_tag_string += char
    return _parse_tags(clean_tag_string)
