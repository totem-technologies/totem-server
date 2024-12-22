import hashlib
import os
from dataclasses import asdict, dataclass
from functools import lru_cache
from io import BytesIO
from math import floor
from typing import Any

import requests
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ImageFile import ImageFile

folder_path = os.path.dirname(os.path.realpath(__file__))
font_path = f"{folder_path}/../static/fonts/Montserrat-VariableFont_wght.ttf"
logo_path = f"{folder_path}/../static/images/totem-logo.png"
client = requests.session()
PADDING = 20


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
        bbox = draw.textbbox((0, 0), temp_line, font=font)
        if bbox[2] <= width:
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
        bbox = draw.textbbox((x, y), line, font=font)
        draw.text((x, y), line, font=font, fill=fill)
        y += (bbox[3] - bbox[1]) + line_height

    return (x, y)


def _draw_avatar(image: Image.Image, avatar_path: str):
    avatar_size = image.height // 3
    target_size = (avatar_size, avatar_size)
    border_color = (255, 255, 255)
    border_width = avatar_size // 50
    canvas = Image.new("RGBA", target_size, border_color)
    input_image = ImageOps.fit(
        _load_img(avatar_path), target_size, centering=(0.5, 0.5), method=Image.Resampling.LANCZOS
    )

    # Make mask
    mask = Image.new("L", target_size, 0)
    draw = ImageDraw.Draw(mask)
    circle_radius = min(target_size[0], target_size[1]) // 2 - border_width
    draw.ellipse(
        (border_width, border_width, circle_radius * 2 + border_width, circle_radius * 2 + border_width), fill=255
    )

    # Apply mask
    input_image.putalpha(mask)
    canvas.putalpha(mask)

    # Composite images together
    canvas.alpha_composite(
        input_image.resize(
            (target_size[0] - border_width * 2, target_size[1] - border_width * 2), resample=Image.Resampling.LANCZOS
        ),
        dest=(border_width, border_width),
    )
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
    scale_factor = (params.width * params.height) // 1000  # Factor is a ratio of width and height.
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
        font_size=scale_factor // 23,
        variation="SemiBold",
    )
    text_position = _draw_wrapped_text(
        image,
        params.time_pst,
        (text_position[0], text_position[1] + 20),
        font_size=scale_factor // 30,
        variation="SemiBold",
    )
    text_position = _draw_wrapped_text(
        image,
        params.time_est,
        (text_position[0], text_position[1] + 20),
        font_size=scale_factor // 30,
        variation="SemiBold",
    )

    # Plop that cherry on top
    _draw_avatar(image, params.author_img_path)
    # _draw_logo(image)
    return image.convert("RGB")


# def image_to_data_url(image: Image.Image):
#     # Save the image in memory as bytes
#     with BytesIO() as output:
#         image.save(output, format="JPEG")
#         contents = output.getvalue()

#     # Encode the bytes as base64 and create a data URL
#     encoded_image = base64.b64encode(contents).decode("utf-8")
#     return f"data:image/png;base64,{encoded_image}"


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
