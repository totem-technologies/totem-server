from taggit.utils import _parse_tags

_illegal_chars = [
    "#",
    ":",
    "!",
    "?",
    "&",
    "(",
    ")",
    "[",
    "]",
    "{",
    "}",
    "/",
    "\\",
    "<",
    ">",
    "*",
    "+",
    "=",
    "|",
    "~",
    "^",
]


def parse_tags(tag_string: str):
    for char in _illegal_chars:
        tag_string = tag_string.replace(char, "")
    return _parse_tags(tag_string)
