import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

import dynimg
from django.conf import settings
from django.template.loader import render_to_string
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


def _is_horizontal(width: int, height: int) -> bool:
    """Use horizontal layout when the card is significantly wider than tall."""
    return width / height >= 1.8


def _title_font_size(title: str, horizontal: bool) -> float:
    """Step down title font size so long titles fit in ~3 lines max."""
    n = len(title)
    if horizontal:
        if n > 70:
            return 6.4
        if n > 50:
            return 7.2
        if n > 35:
            return 8.0
        if n > 20:
            return 9.0
        return 10.0
    else:
        if n > 80:
            return 3.5
        if n > 50:
            return 4.2
        if n > 30:
            return 4.5
        return 5.0


def _base_context(params: CircleImageParams | BlogImageParams) -> dict[str, Any]:
    """Shared template context for all image types."""
    return {
        "width": params.width,
        "height": params.height,
        "horizontal": _is_horizontal(params.width, params.height),
        "max_image_height": int(params.height * 0.65),
        "background_src": _src(params.background_path),
        "avatar_src": _src(params.author_img_path),
        "author_name": params.author_name,
    }


def _circle_html(params: CircleImageParams) -> str:
    ctx = _base_context(params)
    horizontal = ctx["horizontal"]
    ctx.update(
        title=params.title,
        title_font_size=_title_font_size(params.title, horizontal),
        subtitle=params.subtitle,
        day=params.day,
        time_pst=params.time_pst,
        time_est=params.time_est,
    )
    return render_to_string("img_gen/circle.html", ctx)


def _blog_html(params: BlogImageParams) -> str:
    ctx = _base_context(params)
    horizontal = ctx["horizontal"]
    ctx.update(
        label="New on the Totem Blog" if params.show_new else "Totem Blog",
        title=params.title,
        title_font_size=_title_font_size(params.title, horizontal),
    )
    return render_to_string("img_gen/blog.html", ctx)


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
