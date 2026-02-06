import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

import dynimg
from django.conf import settings
from django.template.loader import render_to_string
from PIL import Image as PILImage
from typing_extensions import override


def _generate_hash(data: dict[str, Any], version: int = 1) -> int:  # pyright: ignore[reportExplicitAny]
    sha256_hash = hashlib.sha256()
    input_string = f"{version}:{data}"
    sha256_hash.update(input_string.encode("utf-8"))
    return int.from_bytes(sha256_hash.digest())


@dataclass
class CircleImageParams:
    background_path: str
    author_img_path: str
    author_name: str
    title: str
    subtitle: str
    day: str
    time_pst: str
    time_est: str
    width: int
    height: int

    @override
    def __hash__(self):
        return _generate_hash(asdict(self))


@dataclass
class BlogImageParams:
    background_path: str
    author_img_path: str
    author_name: str
    title: str
    width: int
    height: int
    show_new: bool

    @override
    def __hash__(self):
        return _generate_hash(asdict(self))


def _assets_dir() -> str:
    return os.path.join(str(settings.BASE_DIR), "totem")


def _src(path: str) -> str:
    """Convert a local file path to a path relative to assets_dir.
    HTTP URLs are returned as-is."""
    if path.startswith("http"):
        return path
    return os.path.relpath(os.path.realpath(path), _assets_dir())


def _render(html_content: str, width: int, height: int) -> dynimg.Image:
    options = dynimg.RenderOptions(
        width=width,
        height=height,
        scale=1.0,
        assets_dir=_assets_dir(),
        allow_net=True,
        background="#000000",
    )
    return dynimg.render(html_content, options)


def _max_image_height(width: int, height: int) -> int:
    """Compute max image height in pixels, reserving space for header + details."""
    return int(height * 0.65)


def _get_image_size(bg_path: str) -> tuple[int, int] | None:
    """Get source image dimensions using Pillow. Returns (width, height) or None."""
    if bg_path.startswith("http"):
        return None
    try:
        abs_path = os.path.join(_assets_dir(), bg_path) if not os.path.isabs(bg_path) else bg_path
        with PILImage.open(abs_path) as img:
            return img.size
    except Exception:
        return None


def _content_width(bg_path: str, card_width: int, card_height: int) -> int:
    """Compute the rendered image width so the content wrapper can match it."""
    vmin = min(card_width, card_height)
    available_width = card_width - int(vmin * 0.06)
    max_h = _max_image_height(card_width, card_height)

    size = _get_image_size(bg_path)
    if size is None:
        return available_width

    src_w, src_h = size
    rendered_h = int(available_width * src_h / src_w)
    if rendered_h <= max_h:
        return available_width
    else:
        return int(max_h * src_w / src_h)


def _is_horizontal(width: int, height: int) -> bool:
    """Use horizontal layout when the card is significantly wider than tall."""
    return width / height >= 1.8


def _horizontal_image_width(bg_path: str, card_width: int, card_height: int) -> int:
    """Compute image width for horizontal layout. Image is height-constrained."""
    vmin = min(card_width, card_height)
    available_height = card_height - int(vmin * 0.056)  # top-bar + vertical padding
    max_img_width = int(card_width * 0.5)  # image takes at most 50% of card

    size = _get_image_size(bg_path)
    if size is None:
        return max_img_width

    src_w, src_h = size
    # Image fills available height, compute resulting width
    rendered_width = int(available_height * src_w / src_h)
    return min(rendered_width, max_img_width)


def _circle_html(params: CircleImageParams) -> str:
    bg_src = _src(params.background_path)
    horizontal = _is_horizontal(params.width, params.height)
    return render_to_string(
        "img_gen/circle.html",
        {
            "width": params.width,
            "height": params.height,
            "horizontal": horizontal,
            "max_image_height": _max_image_height(params.width, params.height),
            "content_width": _content_width(params.background_path, params.width, params.height),
            "h_image_width": _horizontal_image_width(params.background_path, params.width, params.height)
            if horizontal
            else 0,
            "background_src": bg_src,
            "avatar_src": _src(params.author_img_path),
            "avatar_size": "28vmin",
            "title": params.title,
            "subtitle": params.subtitle,
            "author_name": params.author_name,
            "day": params.day,
            "time_pst": params.time_pst,
            "time_est": params.time_est,
        },
    )


def _blog_html(params: BlogImageParams) -> str:
    label = "New on the Totem Blog" if params.show_new else "Totem Blog"
    bg_src = _src(params.background_path)
    horizontal = _is_horizontal(params.width, params.height)
    return render_to_string(
        "img_gen/blog.html",
        {
            "width": params.width,
            "height": params.height,
            "horizontal": horizontal,
            "max_image_height": _max_image_height(params.width, params.height),
            "content_width": _content_width(params.background_path, params.width, params.height),
            "h_image_width": _horizontal_image_width(params.background_path, params.width, params.height)
            if horizontal
            else 0,
            "background_src": bg_src,
            "avatar_src": _src(params.author_img_path),
            "avatar_size": "25vmin",
            "label": label,
            "title": params.title,
            "author_name": params.author_name,
        },
    )


@lru_cache(maxsize=100)
def _render_cached(html_hash: int, width: int, height: int, html_content: str) -> dynimg.Image:
    return _render(html_content, width, height)


def generate_circle_image(params: CircleImageParams) -> dynimg.Image:
    html = _circle_html(params)
    return _render_cached(hash(html), params.width, params.height, html)


SpaceImageParams = CircleImageParams
generate_space_image = generate_circle_image


def generate_blog_image(params: BlogImageParams) -> dynimg.Image:
    html = _blog_html(params)
    return _render_cached(hash(html), params.width, params.height, html)


def _test():
    params = CircleImageParams(
        background_path="tests/img_gen/background.jpg",
        author_img_path="tests/img_gen/me.jpg",
        author_name="Bo",
        title="The Addicted Brain",
        subtitle="Rediscovering Moderation",
        day="Jan 10 @ 3:00am PST",
        time_est="Jan 10 @ 3:00am PST",
        time_pst="Jan 10 @ 3:00am PST",
        width=1080,
        height=1080,
    )
    image = generate_circle_image(params)
    image.save_jpeg("tests/img_gen/output.jpg")


if __name__ == "__main__":
    _test()
