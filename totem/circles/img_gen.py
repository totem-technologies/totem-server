import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from io import BytesIO
from math import floor
from typing import Any, Dict, List, Literal, Optional, Tuple

import requests
from django.conf import settings
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ImageFile import ImageFile

folder_path = os.path.dirname(os.path.realpath(__file__))
font_path = f"{folder_path}/../static/fonts/Montserrat-VariableFont_wght.ttf"
font_fallback_path = f"{folder_path}/../static/fonts/NotoSansLiving-Regular.ttf"
font_emoji_path = f"{folder_path}/../static/fonts/TwemojiCOLRv0.ttf"
logo_path = f"{folder_path}/../static/images/totem-logo.png"
client = requests.session()
PADDING = 20


def load_fonts(*font_paths: str) -> Dict[str, TTFont]:
    """
    Loads font files specified by paths into memory and returns a dictionary of font objects.
    """
    fonts = {}
    for path in font_paths:
        font = TTFont(path)
        fonts[path] = font
    return fonts


fonts = load_fonts(font_path, font_fallback_path, font_emoji_path)


@dataclass
class ImageParams:
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
    meta_line: str = ""
    include_avatar: bool = True

    def cache_key(self) -> int:
        # It's important for this to be stable across instances
        # in case it's sent to a shared cache.
        VERSION = 1  # bump to invalidate all them cache
        sha256_hash = hashlib.sha256()
        data_dict = asdict(self)
        input_string = f"{VERSION}:{data_dict}"
        sha256_hash.update(input_string.encode("utf-8"))
        return int.from_bytes(sha256_hash.digest())

    def __hash__(self):
        return self.cache_key()


def adjust_transparency(img: Image.Image, opacity=0.2):
    # factor is a number between 0 and 1
    # Convert the image into RGBA (if not already) and get its pixels
    img = img.convert("RGBA")
    pixels: Any = img.getdata()

    new_pixels = []

    for pixel in pixels:
        # Change the fourth value (alpha) in each pixel according to opacity percentage
        new_pixel = (pixel[0], pixel[1], pixel[2], int(opacity * pixel[3]))
        new_pixels.append(new_pixel)

    # Update the pixels of the image with our newly modified pixels and return it
    img.putdata(new_pixels)
    return img


def _make_gradient(image):
    gradient_overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient_overlay)
    for y in range(image.height):
        alpha = int((1 - y / image.height) * 160)  # Adjust the gradient direction as needed
        draw.line([(0, y), (image.width, y)], fill=(0, 0, 0, alpha), width=1)
    return Image.alpha_composite(image, gradient_overlay)


def _resize(original_image: ImageFile, target_width, target_height):
    aspect_ratio = original_image.width / float(original_image.height)
    if target_width / target_height < aspect_ratio:
        new_width = int(target_height * aspect_ratio)
        resized_image = original_image.resize((new_width, target_height), resample=Image.Resampling.LANCZOS)
        x0 = (new_width - target_width) // 2
        cropped_image = resized_image.crop((x0, 0, x0 + target_width, target_height))
    else:
        new_height = int(target_width / aspect_ratio)
        resized_image = original_image.resize((target_width, new_height), resample=Image.Resampling.LANCZOS)
        y0 = (new_height - target_height) // 2
        cropped_image = resized_image.crop((0, y0, target_width, y0 + target_height))
    return cropped_image


def _wrap_text(text, width, font):
    lines = []
    if not text:
        return lines

    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    words = text.split()
    line = ""

    for word in words:
        temp_line = f"{line} {word}" if line else word
        b_box = draw.textbbox((0, 0), temp_line, font=font)
        if b_box[2] <= width - 50:  # 50 fudge factor to account for emoji
            line = temp_line
        else:
            lines.append(line)
            line = word
    lines.append(line)
    return lines


def _draw_wrapped_text(
    image: Image.Image, text, position, font_size: int = 14, variation: str = "SemiBold", fill: str = "white"
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
        # draw.text((x, y), line, font=font, fill=fill)
        draw_multiline_text_v2(draw, (x, y), line, (255, 255, 255), fonts, font_size, variation, align="left")
        y += (b_box[3] - b_box[1]) + line_height

    return (x, y)


def _draw_avatar(image: Image.Image, avatar_path: str):
    avatar_size = 400
    target_size = (avatar_size, avatar_size)
    border_color = (255, 255, 255)
    border_width = avatar_size // 50

    # Use supersampling for smoother edges
    scale_factor = 4  # 4x supersampling
    hi_res_size = (avatar_size * scale_factor, avatar_size * scale_factor)

    # Create high-resolution masks for anti-aliasing
    # 1. Outer mask (full circle including border)
    hi_res_outer_mask = Image.new("L", hi_res_size, 0)
    draw_outer = ImageDraw.Draw(hi_res_outer_mask)
    draw_outer.ellipse((0, 0, hi_res_size[0], hi_res_size[1]), fill=255)

    # Downsample outer mask to target size using high-quality interpolation
    outer_mask = hi_res_outer_mask.resize(target_size, resample=Image.Resampling.LANCZOS)

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
    avatar_mask = hi_res_avatar_mask.resize(avatar_mask_size, resample=Image.Resampling.LANCZOS)

    # Create a properly sized and positioned avatar with mask
    avatar_with_mask = Image.new("RGBA", target_size, (0, 0, 0, 0))
    avatar_with_mask.paste(avatar_img, (border_width, border_width), avatar_mask)

    # Combine the white border and the avatar
    canvas.alpha_composite(avatar_with_mask)

    # Add to main image
    image.alpha_composite(canvas, dest=(image.width - canvas.width - PADDING, image.height - canvas.width - PADDING))
    # Uncomment to see avatar render
    # canvas.save("circular_avatar.png")


def _draw_logo(image: Image.Image):
    logo = Image.open(logo_path).convert("RGBA")
    scale_factor = image.height / 10000
    logo_size_height = floor(logo.height * scale_factor)
    logo_size_width = floor(logo.width * scale_factor)
    logo = logo.resize((logo_size_width, logo_size_height))
    logo = adjust_transparency(logo)
    image.alpha_composite(logo, dest=(PADDING, image.height - logo.height - PADDING))


def _load_img(path: str):
    if path.startswith("http"):
        resp = client.get(path, timeout=10, verify=not settings.DEBUG)
        img = Image.open(BytesIO(resp.content))
        return img
    else:
        return Image.open(path)


@lru_cache(maxsize=100)
def generate_image(params: ImageParams):
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
        font_size=scale_factor // 20,
        variation="Regular",
    )

    if params.meta_line:
        # If meta_line provided (e.g., "By Author • Jan 1, 2025"), render that instead of event-specific lines
        text_position = _draw_wrapped_text(
            image,
            params.meta_line,
            (text_position[0], text_position[1] + 10),
            font_size=scale_factor // 30,
            variation="Regular",
        )
    else:
        # Default event-specific rendering
        text_position = _draw_wrapped_text(
            image,
            f"with {params.author_name} @ totem.org",
            (text_position[0], text_position[1] + 10),
            font_size=scale_factor // 30,
            variation="Regular",
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
    if params.include_avatar:
        _draw_avatar(image, params.author_img_path)
    # _draw_logo(image)
    return image.convert("RGB")


def has_glyph(font: TTFont, glyph: str) -> bool:
    """
    Checks if the given font contains a glyph for the specified character.
    """
    for table in font["cmap"].tables:  # type: ignore
        if table.cmap.get(ord(glyph)):
            return True
    return False


def merge_chunks(text: str, fonts: Dict[str, TTFont]) -> List[List[str]]:
    """
    Merges consecutive characters with the same font into clusters, optimizing font lookup.
    """
    chunks = []

    for char in text:
        for font_path, font in fonts.items():
            if has_glyph(font, char):
                chunks.append([char, font_path])
                break

    cluster = chunks[:1]

    for char, font_path in chunks[1:]:
        if cluster[-1][1] == font_path:
            cluster[-1][0] += char
        else:
            cluster.append([char, font_path])

    return cluster


def draw_text_v2(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    color: Tuple[int, int, int],
    fonts: Dict[str, TTFont],
    variation: str,
    size: int,
    anchor: Optional[str] = None,
    align: Literal["left", "center", "right"] = "left",
) -> None:
    """
    Draws text on an image at given coordinates, using specified size, color, and fonts.
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
        draw.text(
            xy=xy_,
            text=words[0],
            fill=color,
            font=font,
            variation=variation,
            anchor=anchor,
            align=align,
            embedded_color=True,
        )

        draw.text
        box = font.getbbox(words[0])
        y_offset += box[2] - box[0]


def draw_multiline_text_v2(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    color: Tuple[int, int, int],
    fonts: Dict[str, TTFont],
    size: int,
    variation: str,
    anchor: Optional[str] = None,
    align: Literal["left", "center", "right"] = "left",
) -> None:
    """
    Draws multiple lines of text on an image, handling newline characters and adjusting spacing between lines.
    """
    spacing = xy[1]
    lines = text.split("\n")

    for line in lines:
        mod_cord = (xy[0], spacing)
        draw_text_v2(
            draw,
            xy=mod_cord,
            text=line,
            color=color,
            fonts=fonts,
            variation=variation,
            size=size,
            anchor=anchor,
            align=align,
        )
        spacing += size + 5


def _test():
    params = ImageParams(
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
    image = generate_image(params)
    # Save the result
    image.save(
        "tests/img_gen/output.jpg",
        optimize=True,
    )


if __name__ == "__main__":
    _test()
