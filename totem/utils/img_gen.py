import hashlib
import os
from collections.abc import Sequence
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
from uniseg.graphemecluster import grapheme_clusters

folder_path = os.path.dirname(os.path.realpath(__file__))
font_path = f"{folder_path}/../static/fonts/Montserrat-VariableFont_wght.ttf"
font_fallback_path = f"{folder_path}/../static/fonts/NotoSansLiving-Regular.ttf"
font_emoji_path = f"{folder_path}/../static/fonts/TwemojiCOLRv0.ttf"
logo_path = f"{folder_path}/../static/images/totem-logo.png"
client = requests.session()
PADDING = 20


def load_fonts(*font_paths: str) -> dict[str, set[int]]:
    """
    Loads font files and extracts cmap codepoints as simple sets.
    This avoids thread-safety issues with TTFont's lazy loading.
    """
    fonts: dict[str, set[int]] = {}
    for path in font_paths:
        font = TTFont(path)
        codepoints: set[int] = set()
        for table in font["cmap"].tables:  # pyright: ignore[reportAttributeAccessIssue, reportUnknownMemberType, reportUnknownVariableType]
            if hasattr(table, "cmap") and table.cmap:
                codepoints.update(table.cmap.keys())  # pyright: ignore[reportUnknownMemberType]
        fonts[path] = codepoints
        font.close()
    return fonts


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


def has_glyph(codepoints: set[int], glyph: str) -> bool:
    """
    Checks if the given font codepoint set contains all codepoints in the grapheme cluster.
    For ZWJ sequences like family emojis, all component codepoints must be present.
    """
    return all(ord(char) in codepoints for char in glyph)


def merge_chunks(text: str, fonts: dict[str, set[int]]) -> list[tuple[str, str]]:
    """
    Merges consecutive grapheme clusters with the same font into chunks,
    optimizing font lookup.
    Uses grapheme clusters to properly handle ZWJ emoji sequences like 👨‍👨‍👧‍👦.
    Mostly used to switch to the emoji font when an emoji is detected to avoid
    the dreaded empty square.
    """
    chunks: list[tuple[str, str]] = []

    for cluster in grapheme_clusters(text):
        for path, codepoints in fonts.items():
            if has_glyph(codepoints, cluster):
                chunks.append((cluster, path))
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
    fonts: dict[str, set[int]],
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
        # No stroke/border on text for clean appearance
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
            stroke_fill=(0, 0, 0),
        )

        box = font.getbbox(words[0])
        y_offset += box[2] - box[0]


@lru_cache(maxsize=100)
def generate_circle_image(params: CircleImageParams):  
    """
    Generates a circle/event promotional image following the Figma design.
    
    Layout structure:
    - Top: Centered title and subtitle
    - Middle: Rounded rectangle featured image with shadow
    - Below image: Author name + avatar (horizontal layout)
    - Bottom: Date on left, times on right
    - Background: Radial gradient from top-left (warm yellow) to bottom-center (cool purple/pink)
    """
    
    # Create canvas with gradient background
    # Gradient flows from top-left (warm yellow) to bottom-center (cool purple/pink)
    canvas = Image.new("RGB", (params.width, params.height), (0, 0, 0))
    
    # Generate radial gradient from top-left to bottom-center using efficient Pillow methods
    # Start color: warm yellow/gold (#F5D67A)
    # End color: purple/pink (#C49BA8)
    start_color = (245, 214, 122)  # Yellow/gold at top-left
    end_color = (196, 155, 168)    # Purple/pink at bottom-center
    
    # Origin point (top-left)
    origin_x, origin_y = 0, 0
    # Target point (bottom-center)
    target_x, target_y = params.width // 2, params.height
    
    # Calculate maximum distance for gradient spread
    max_distance = ((target_x - origin_x) ** 2 + (target_y - origin_y) ** 2) ** 0.5
    
    # Pre-calculate all pixel colors efficiently using list comprehension
    # This is much faster than calling draw.point() for each pixel
    pixels = []
    for y in range(params.height):
        for x in range(params.width):
            # Calculate distance from origin (top-left) to current pixel
            distance = ((x - origin_x) ** 2 + (y - origin_y) ** 2) ** 0.5
            # Normalize distance to 0-1 range
            ratio = min(distance / max_distance, 1.0)
            
            # Interpolate color based on distance
            r = int(start_color[0] * (1 - ratio) + end_color[0] * ratio)
            g = int(start_color[1] * (1 - ratio) + end_color[1] * ratio)
            b = int(start_color[2] * (1 - ratio) + end_color[2] * ratio)
            
            pixels.append((r, g, b))
    
    # Use Pillow's efficient putdata method to set all pixels at once
    canvas.putdata(pixels)  # pyright: ignore[reportUnknownMemberType]
    
    # Convert to RGBA for compositing with alpha channel support
    canvas = canvas.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    
    # Scale factor for responsive sizing (based on 1080px design)
    scale_factor = params.width / 1080
    
    # === TOP SECTION: Title and Subtitle (Centered) ===
    title_font_size = int(63 * scale_factor)
    subtitle_font_size = int(44 * scale_factor)
    title_y = int(84 * scale_factor)  # Top padding + space
    
    # Draw centered title
    title_font = ImageFont.truetype(font_path, title_font_size)
    title_font.set_variation_by_name("SemiBold")
    
    # Wrap title text for centering
    title_lines = _wrap_text(params.title, params.width - 40, title_font)
    title_line_height = int(title_font_size * 1.2)
    
    current_y = title_y
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        text_width = bbox[2] - bbox[0]
        x_centered = (params.width - text_width) // 2
        
        draw_text(
            draw,
            xy=(x_centered, current_y),
            text=line,
            color=(255, 255, 255),
            fonts=fonts,
            variation="SemiBold",
            size=title_font_size,
            anchor=None,
            align="center",
        )
        current_y += title_line_height
    
    # Draw centered subtitle
    subtitle_y = current_y + int(20 * scale_factor)
    subtitle_font = ImageFont.truetype(font_path, subtitle_font_size)
    subtitle_font.set_variation_by_name("SemiBold")
    
    subtitle_lines = _wrap_text(params.subtitle, params.width - 40, subtitle_font)
    subtitle_line_height = int(subtitle_font_size * 2)  # Line height 2 per design
    
    for line in subtitle_lines:
        bbox = draw.textbbox((0, 0), line, font=subtitle_font)
        text_width = bbox[2] - bbox[0]
        x_centered = (params.width - text_width) // 2
        
        draw_text(
            draw,
            xy=(x_centered, subtitle_y),
            text=line,
            color=(255, 255, 255),
            fonts=fonts,
            variation="SemiBold",
            size=subtitle_font_size,
            anchor=None,
            align="center",
        )
        subtitle_y += subtitle_line_height
    
    # === MIDDLE SECTION: Featured Image (Rounded Rectangle with Shadow) ===
    featured_img = _load_img(params.background_path)
    img_width = int(602 * scale_factor)
    img_height = int(380 * scale_factor)
    border_radius = int(30 * scale_factor)
    
    # Resize and crop featured image
    featured_img = ImageOps.fit(
        featured_img,
        (img_width, img_height),
        centering=(0.5, 0.5),
        method=Image.Resampling.LANCZOS
    ).convert("RGBA")
    
    # Create rounded rectangle mask for the image
    mask = Image.new("L", (img_width, img_height), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle(
        [(0, 0), (img_width, img_height)],
        radius=border_radius,
        fill=255
    )
    
    # Apply mask to create rounded image
    rounded_img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    rounded_img.paste(featured_img, (0, 0), mask)
    
    # Position image centered horizontally, below subtitle
    img_x = (params.width - img_width) // 2
    img_y = subtitle_y + int(20 * scale_factor)
    
    # Create shadow effect (simple dark rectangle behind, slightly offset)
    shadow_offset = int(5 * scale_factor)
    shadow_blur = int(12 * scale_factor)
    shadow = Image.new("RGBA", (img_width + shadow_blur * 2, img_height + shadow_blur * 2), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        [(shadow_blur, shadow_blur), (img_width + shadow_blur, img_height + shadow_blur)],
        radius=border_radius,
        fill=(0, 0, 0, 64)  # Semi-transparent black
    )
    
    # Composite shadow and image onto canvas
    canvas.alpha_composite(
        shadow,
        dest=(img_x - shadow_blur + shadow_offset, img_y - shadow_blur + shadow_offset)
    )
    canvas.alpha_composite(rounded_img, dest=(img_x, img_y))
    
    # === AUTHOR SECTION: Name + Avatar (Horizontal) ===
    author_section_y = img_y + img_height + int(20 * scale_factor)
    author_font_size = int(35 * scale_factor)
    avatar_size = int(150 * scale_factor)
    
    # Calculate center position for author section
    author_section_width = int(500 * scale_factor)  # Approximate width for text + avatar + gap
    author_x = (params.width - author_section_width) // 2
    
    # Draw author text (right-aligned to avatar)
    author_font = ImageFont.truetype(font_path, author_font_size)
    author_font.set_variation_by_name("SemiBold")
    
    author_line1 = f"with {params.author_name}"
    author_line2 = "@totem.org"
    
    # Get text dimensions for positioning
    bbox1 = draw.textbbox((0, 0), author_line1, font=author_font)
    bbox2 = draw.textbbox((0, 0), author_line2, font=author_font)
    text_width = max(bbox2[2] - bbox2[0], bbox1[2] - bbox1[0])
    
    # Position text to the left of avatar
    text_x = (params.width - text_width - int(20 * scale_factor) - avatar_size) // 2
    text_y = author_section_y + (avatar_size - int(author_font_size * 2.2)) // 2
    
    draw_text(
        draw,
        xy=(text_x, text_y),
        text=author_line1,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=author_font_size,
        anchor=None,
        align="left",
    )
    
    draw_text(
        draw,
        xy=(text_x, text_y + int(author_font_size * 1.2)),
        text=author_line2,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=author_font_size,
        anchor=None,
        align="left",
    )
    
    # Draw avatar (circular, to the right of text)
    avatar_x = text_x + text_width + int(20 * scale_factor)
    avatar_y = author_section_y
    
    # Load and create circular avatar
    avatar_img = _load_img(params.author_img_path)
    avatar_img = ImageOps.fit(
        avatar_img,
        (avatar_size, avatar_size),
        centering=(0.5, 0.5),
        method=Image.Resampling.LANCZOS
    ).convert("RGBA")
    
    # Create circular mask with white border
    border_width = int(4 * scale_factor)
    avatar_with_border = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
    avatar_draw = ImageDraw.Draw(avatar_with_border)
    
    # Draw white circle border
    avatar_draw.ellipse([(0, 0), (avatar_size, avatar_size)], fill=(255, 255, 255))
    
    # Create inner mask for avatar
    inner_size = avatar_size - border_width * 2
    inner_mask = Image.new("L", (inner_size, inner_size), 0)
    inner_draw = ImageDraw.Draw(inner_mask)
    inner_draw.ellipse([(0, 0), (inner_size, inner_size)], fill=255)
    
    # Resize avatar to fit inside border
    avatar_inner = ImageOps.fit(
        avatar_img,
        (inner_size, inner_size),
        centering=(0.5, 0.5),
        method=Image.Resampling.LANCZOS
    )
    
    # Composite avatar onto white circle
    avatar_with_border.paste(avatar_inner, (border_width, border_width), inner_mask)
    
    # Add avatar to canvas
    canvas.alpha_composite(avatar_with_border, dest=(avatar_x, avatar_y))
    
    # === BOTTOM SECTION: Date and Times ===
    bottom_y = author_section_y + avatar_size + int(40 * scale_factor)
    date_time_font_size = int(35 * scale_factor)
    date_time_font = ImageFont.truetype(font_path, date_time_font_size)
    date_time_font.set_variation_by_name("SemiBold")
    
    # Left side: Date (split into two lines if needed)
    date_parts = params.day.split()  # e.g., "27 October"
    date_x = int(50 * scale_factor)
    
    # Draw date line 1 (e.g., "27 October")
    draw_text(
        draw,
        xy=(date_x, bottom_y),
        text=date_parts[0] if len(date_parts) > 0 else params.day,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=date_time_font_size,
        anchor=None,
        align="left",
    )
    
    # Draw year on second line (extract year if present, otherwise use "2025")
    year_text = "2025"  # Default
    for part in date_parts:
        if part.isdigit() and len(part) == 4:
            year_text = part
    
    draw_text(
        draw,
        xy=(date_x, bottom_y + int(date_time_font_size * 1.2)),
        text=year_text,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=date_time_font_size,
        anchor=None,
        align="left",
    )
    
    # Right side: Times (right-aligned)
    time_x = params.width - int(50 * scale_factor)
    
    # Get text widths for right alignment
    bbox_est = draw.textbbox((0, 0), params.time_est, font=date_time_font)
    bbox_pst = draw.textbbox((0, 0), params.time_pst, font=date_time_font)
    est_width = bbox_est[2] - bbox_est[0]
    pst_width = bbox_pst[2] - bbox_pst[0]
    
    # Draw EST time (top)
    draw_text(
        draw,
        xy=(time_x - est_width, bottom_y),
        text=params.time_est,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=date_time_font_size,
        anchor=None,
        align="right",
    )
    
    # Draw PST time (bottom)
    draw_text(
        draw,
        xy=(time_x - pst_width, bottom_y + int(date_time_font_size * 1.2)),
        text=params.time_pst,
        color=(255, 255, 255),
        fonts=fonts,
        variation="SemiBold",
        size=date_time_font_size,
        anchor=None,
        align="right",
    )
    
    return canvas.convert("RGB")


SpaceImageParams = CircleImageParams
generate_space_image = generate_circle_image


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
        font_size=scale_factor // 25,
    )
    text_position = _draw_wrapped_text(
        image,
        params.title,
        (text_position[0], text_position[1] + spacing),
        font_size=scale_factor // 13,
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
