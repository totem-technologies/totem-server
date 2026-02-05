import hashlib
import html
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Any

import dynimg
from django.conf import settings
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
    """Convert a file path or URL to a src suitable for use in HTML."""
    if path.startswith("http"):
        return html.escape(path)
    abs_path = os.path.realpath(path)
    return html.escape(os.path.relpath(abs_path, _assets_dir()))


_BASE_CSS = """
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
        font-family: 'Montserrat', sans-serif;
        color: white;
        overflow: hidden;
        display: flex;
        flex-direction: column;
    }
    .bg {
        position: absolute;
        inset: 0;
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .gradient {
        position: absolute;
        inset: 0;
        background: linear-gradient(to bottom, rgba(0,0,0,0.63), transparent);
    }
    .content {
        position: relative;
        flex: 1;
        display: flex;
        flex-direction: column;
        padding: 2vmin;
        overflow: hidden;
    }
    .avatar {
        position: absolute;
        bottom: 2vmin;
        right: 2vmin;
        border-radius: 50%;
        border: 0.5vmin solid white;
        object-fit: cover;
    }
"""


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
    return f"""<!DOCTYPE html>
<html>
<head><style>
{_BASE_CSS}
</style></head>
<body style="width: {params.width}px; height: {params.height}px; position: relative;">
    <img class="bg" src="{_src(params.background_path)}" />
    <div class="gradient"></div>
    <div class="content">
        <div style="font-size: 9.5vh; font-weight: 600; line-height: 1.1;">{html.escape(params.title)}</div>
        <div style="font-size: 3.7vh; font-weight: 600; margin-top: 2vh;">{html.escape(params.subtitle)}</div>
        <div style="font-size: 3.7vh; font-weight: 600; margin-top: 1vh;">with {html.escape(params.author_name)} @ totem.org</div>
        <div style="font-size: 5.2vh; font-weight: 600; margin-top: 3vh;">{html.escape(params.day)}</div>
        <div style="font-size: 5.2vh; font-weight: 600; margin-top: 1.5vh;">{html.escape(params.time_pst)}</div>
        <div style="font-size: 5.2vh; font-weight: 600; margin-top: 1.5vh;">{html.escape(params.time_est)}</div>
    </div>
    <img class="avatar" src="{_src(params.author_img_path)}" style="width: 28vmin; height: 28vmin;" />
</body>
</html>"""


def _blog_html(params: BlogImageParams) -> str:
    label = "New on the Totem Blog" if params.show_new else "Totem Blog"
    return f"""<!DOCTYPE html>
<html>
<head><style>
{_BASE_CSS}
</style></head>
<body style="width: {params.width}px; height: {params.height}px; position: relative;">
    <img class="bg" src="{_src(params.background_path)}" />
    <div class="gradient"></div>
    <div class="content">
        <div style="font-size: 3.7vh; font-weight: 600;">{html.escape(label)}</div>
        <div style="font-size: 7vh; font-weight: 600; margin-top: 2vh; line-height: 1.1;">{html.escape(params.title)}</div>
        <div style="font-size: 3.7vh; font-weight: 600; margin-top: 2vh;">by {html.escape(params.author_name)} @ totem.org</div>
    </div>
    <img class="avatar" src="{_src(params.author_img_path)}" style="width: 25vmin; height: 25vmin;" />
</body>
</html>"""


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
