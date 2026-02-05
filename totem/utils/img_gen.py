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


def _circle_html(params: CircleImageParams) -> str:
    return render_to_string(
        "img_gen/circle.html",
        {
            "width": params.width,
            "height": params.height,
            "background_src": _src(params.background_path),
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
    return render_to_string(
        "img_gen/blog.html",
        {
            "width": params.width,
            "height": params.height,
            "background_src": _src(params.background_path),
            "avatar_src": _src(params.author_img_path),
            "avatar_size": "25vmin",
            "label": label,
            "title": params.title,
            "author_name": params.author_name,
        },
    )


@lru_cache(maxsize=100)
def generate_circle_image(params: CircleImageParams) -> dynimg.Image:
    return _render(_circle_html(params), params.width, params.height)


SpaceImageParams = CircleImageParams
generate_space_image = generate_circle_image


@lru_cache(maxsize=100)
def generate_blog_image(params: BlogImageParams) -> dynimg.Image:
    return _render(_blog_html(params), params.width, params.height)


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
