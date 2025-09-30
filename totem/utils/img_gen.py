from collections.abc import Sequence
import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from io import BytesIO
from typing import Any, Literal, cast

import requests
from django.conf import settings
from fontTools.ttLib import TTFont  # pyright: ignore[reportMissingTypeStubs]
from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ImageFile import ImageFile
from typing_extensions import override

folder_path = os.path.dirname(os.path.realpath(__file__))
font_path = f"{folder_path}/../static/fonts/Montserrat-VariableFont_wght.ttf"
font_fallback_path = f"{folder_path}/../static/fonts/NotoSansLiving-Regular.ttf"
font_emoji_path = f"{folder_path}/../static/fonts/TwemojiCOLRv0.ttf"
logo_path = f"{folder_path}/../static/images/totem-logo.png"
client = requests.session()
PADDING = 20


def load_fonts(*font_paths: str) -> dict[str, TTFont]:
    """
    Loads font files specified by paths into memory and returns a dictionary of font objects.
    """
    fonts = {}
    for path in font_paths:
        font = TTFont(path)
        fonts[path] = font
    return cast(dict[str, TTFont], fonts)


fonts = load_fonts(font_path, font_fallback_path, font_emoji_path)


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


def adjust_transparency(img: Image.Image, opacity: float = 0.2):
    # factor is a number between 0 and 1
    # Convert the image into RGBA (if not already) and get its pixels
    img = img.convert("RGBA")
    pixels = cast(Sequence[tuple[int, int, int, int]], img.getdata())  # pyright: ignore[reportUnknownMemberType]
    new_pixels: list[tuple[int, int, int, int]] = []

    for pixel in pixels:
        # Change the fourth value (alpha) in each pixel according to opacity percentage
        new_pixel = (pixel[0], pixel[1], pixel[2], int(opacity * pixel[3]))
        new_pixels.append(new_pixel)

    # Update the pixels of the image with our newly modified pixels and return it
    img.putdata(new_pixels)  # pyright: ignore[reportUnknownMemberType]
    return img


def _make_gradient(image: Image.Image):
    gradient_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient_overlay)
    for y in range(image.height):
        alpha = int((1 - y / image.height) * 160)  # Adjust the gradient direction as needed
        draw.line([(0, y), (image.width, y)], fill=(0, 0, 0, alpha), width=1)
    return Image.alpha_composite(image, gradient_overlay)


def _resize(original_image: ImageFile, target_width: int, target_height: int):
    aspect_ratio = original_image.width / float(original_image.height)
    if target_width / target_height < aspect_ratio:
        new_width = int(target_height * aspect_ratio)
        resized_image = original_image.resize((new_width, target_height), resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
        x0 = (new_width - target_width) // 2
        cropped_image = resized_image.crop((x0, 0, x0 + target_width, target_height))
    else:
        new_height = int(target_width / aspect_ratio)
        resized_image = original_image.resize((target_width, new_height), resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]
        y0 = (new_height - target_height) // 2
        cropped_image = resized_image.crop((0, y0, target_width, y0 + target_height))
    return cropped_image


def _wrap_text(text: str, width: int, font: ImageFont.FreeTypeFont) -> list[str]:
    lines: list[str] = []
    if not text:
        return lines

    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words = text.split()
    line = ""

    for word in words:
        temp_line = f"{line} {word}" if line else word
        b_box = draw.textbbox((0, 0), temp_line, font=font)
        if b_box[2] <= width - 60:  # 50 fudge factor to account for emoji
            line = temp_line
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _draw_wrapped_text(
    image: Image.Image,
    text: str,
    position: tuple[int, int],
    font_size: int = 14,
    variation: str = "SemiBold",
):
    draw = ImageDraw.Draw(image)
    x, y = position
    wrap_width = image.width - x
    line_height = font_size // 4
    font = ImageFont.truetype(font_path, font_size)
    font.set_variation_by_name(variation)
    lines = _wrap_text(text, wrap_width, font)

    for line in lines:
        b_box = draw.textbbox((x, y), line, font=font)
        draw_text(
            draw,
            xy=(x, y),
            text=line,
            color=(255, 255, 255),
            fonts=fonts,
            variation=variation,
            size=font_size,
            anchor=None,
            align="left",
        )
        y += round((b_box[3] - b_box[1]) + line_height)

    return (x, y)


def _draw_avatar(image: Image.Image, avatar_path: str, avatar_size: int = 400):
    target_size = (avatar_size, avatar_size)
    border_color = (255, 255, 255)
    border_width = avatar_size // 50

    # Use super sampling for smoother edges
    scale_factor = 4  # 4x super sampling
    hi_res_size = (avatar_size * scale_factor, avatar_size * scale_factor)

    # Create high-resolution masks for anti-aliasing
    # 1. Outer mask (full circle including border)
    hi_res_outer_mask = Image.new("L", hi_res_size, 0)
    draw_outer = ImageDraw.Draw(hi_res_outer_mask)
    draw_outer.ellipse((0, 0, hi_res_size[0], hi_res_size[1]), fill=255)

    # Down sample outer mask to target size using high-quality interpolation
    outer_mask = hi_res_outer_mask.resize(target_size, resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]

    # Create a new transparent canvas
    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))

    # Create the white border circle (full white circle with the outer mask)
    border_circle = Image.new("RGBA", target_size, border_color)
    border_circle.putalpha(outer_mask)

    # Add the border circle to the canvas
    canvas.paste(border_circle, (0, 0), outer_mask)

    # Load and fit the avatar image
    avatar_img = _load_img(avatar_path)
    avatar_size_inner = target_size[0] - border_width * 2
    avatar_img = ImageOps.fit(
        avatar_img, (avatar_size_inner, avatar_size_inner), centering=(0.5, 0.5), method=Image.Resampling.LANCZOS
    )

    # Create a mask specifically for the avatar image
    avatar_mask_size = (avatar_size_inner, avatar_size_inner)
    hi_res_avatar_mask = Image.new("L", (avatar_mask_size[0] * scale_factor, avatar_mask_size[1] * scale_factor), 0)
    draw_avatar_mask = ImageDraw.Draw(hi_res_avatar_mask)
    draw_avatar_mask.ellipse((0, 0, hi_res_avatar_mask.width, hi_res_avatar_mask.height), fill=255)
    avatar_mask = hi_res_avatar_mask.resize(avatar_mask_size, resample=Image.Resampling.LANCZOS)  # pyright: ignore[reportUnknownMemberType]

    # Create a properly sized and positioned avatar with mask
    avatar_with_mask = Image.new("RGBA", target_size, (0, 0, 0, 0))
    avatar_with_mask.paste(avatar_img, (border_width, border_width), avatar_mask)

    # Combine the white border and the avatar
    canvas.alpha_composite(avatar_with_mask)

    # Add to main image
    image.alpha_composite(canvas, dest=(image.width - canvas.width - PADDING, image.height - canvas.width - PADDING))
    # Uncomment to see avatar render
    # canvas.save("circular_avatar.png")


def _load_img(path: str):
    if path.startswith("http"):
        resp = client.get(path, timeout=10, verify=not settings.DEBUG)  # pyright: ignore[reportAny]
        img = Image.open(BytesIO(resp.content))
        return img
    else:
        return Image.open(path)


def has_glyph(font: TTFont, glyph: str) -> bool:
    """
    Checks if the given font contains a glyph for the specified character.
    """
    for table in font["cmap"].tables:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
        if table.cmap.get(ord(glyph)):  # pyright: ignore[reportUnknownMemberType]
            return True
    return False


def merge_chunks(text: str, fonts: dict[str, TTFont]) -> list[tuple[str, str]]:
    """
    Merges consecutive characters with the same font into clusters,
    optimizing font lookup.
    Mostly used to switch to the emoji font when a emoji is detected to avoid
    the dreaded empty square.
    """
    chunks: list[tuple[str, str]] = []

    for char in text:
        for font_path, font in fonts.items():
            if has_glyph(font, char):
                chunks.append((char, font_path))
                break

    cluster = chunks[:1]

    for char, font_path in chunks[1:]:
        if cluster[-1][1] == font_path:
            cluster[-1] = (cluster[-1][0] + char, font_path)
        else:
            cluster.append((char, font_path))

    return cluster


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    color: tuple[int, int, int],
    fonts: dict[str, TTFont],
    variation: str,
    size: int,
    anchor: str | None = None,
    align: Literal["left", "center", "right"] = "left",
) -> None:
    """
    Draws text on an image at given coordinates,
    using specified size, color, and fonts.
    """

    y_offset = 0
    sentence = merge_chunks(text, fonts)

    for words in sentence:
        xy_ = (xy[0] + y_offset, xy[1])

        font = ImageFont.truetype(words[1], size)
        try:
            font.set_variation_by_name(variation)
        except OSError:
            # Some fonts don't support variations, and that's OK.
            pass
        stroke_width = 2
        if size < 100:
            stroke_width = 1
        if words[1] == font_emoji_path:
            stroke_width = 0
        draw.text(
            xy=xy_,
            text=words[0],
            fill=color,
            font=font,
            variation=variation,
            anchor=anchor,
            align=align,
            embedded_color=True,
            stroke_width=stroke_width,
            stroke_fill=(
                0,
                0,
                0,
            ),
        )

        box = font.getbbox(words[0])
        y_offset += box[2] - box[0]


@lru_cache(maxsize=100)
def generate_circle_image(params: CircleImageParams):
    image = _load_img(params.background_path)  # Replace with your image path
    image = _resize(image, params.width, params.height).convert("RGBA")
    image = _make_gradient(image)

    # Set up text
    text_position = (PADDING, PADDING)  # (x, y) coordinates
    scale_factor = 1000
    spacing = scale_factor // 30

    # Draw text on image
    text_position = _draw_wrapped_text(image, params.title, text_position, font_size=scale_factor // 10)
    text_position = _draw_wrapped_text(
        image,
        params.subtitle,
        (text_position[0], text_position[1] + spacing),
        font_size=scale_factor // 25,
        variation="SemiBold",
    )

    # Default event-specific rendering
    text_position = _draw_wrapped_text(
        image,
        f"with {params.author_name} @ totem.org",
        (text_position[0], text_position[1] + 10),
        font_size=scale_factor // 25,
        variation="SemiBold",
    )
    text_position = _draw_wrapped_text(
        image,
        params.day,
        (text_position[0], text_position[1] + 30),
        font_size=scale_factor // 18,
        variation="SemiBold",
    )
    text_position = _draw_wrapped_text(
        image,
        params.time_pst,
        (text_position[0], text_position[1] + 20),
        font_size=scale_factor // 18,
        variation="SemiBold",
    )
    text_position = _draw_wrapped_text(
        image,
        params.time_est,
        (text_position[0], text_position[1] + 20),
        font_size=scale_factor // 18,
        variation="SemiBold",
    )

    # Plop that cherry on top (optional for blog)
    _draw_avatar(image, params.author_img_path, 300)
    # _draw_logo(image)
    return image.convert("RGB")


@lru_cache(maxsize=100)
def generate_blog_image(params: BlogImageParams):
    image = _load_img(params.background_path)  # Replace with your image path
    image = _resize(image, params.width, params.height).convert("RGBA")
    image = _make_gradient(image)

    # Set up text
    text_position = (PADDING, PADDING)  # (x, y) coordinates
    scale_factor = 1000
    spacing = scale_factor // 30

    # Draw text on image
    if params.show_new:
        label_text = "New on the Totem Blog"
    else:
        label_text = "Totem Blog"
    text_position = _draw_wrapped_text(
        image,
        label_text,
        text_position,
        font_size=scale_factor // 20,
    )
    text_position = _draw_wrapped_text(
        image,
        params.title,
        (text_position[0], text_position[1] + spacing),
        font_size=scale_factor // 12,
    )

    # Default event-specific rendering
    text_position = _draw_wrapped_text(
        image,
        f"by {params.author_name} @ totem.org",
        (text_position[0], text_position[1] + spacing),
        font_size=scale_factor // 25,
    )
    avatar_size = min(params.height, params.width) // 4
    # Plop that cherry on top
    _draw_avatar(image, params.author_img_path, avatar_size)
    return image.convert("RGB")


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
        # width=1024,
        # height=512,
    )
    image = generate_circle_image(params)
    # Save the result
    image.save(
        "tests/img_gen/output.jpg",
        optimize=True,
    )


if __name__ == "__main__":
    _test()
