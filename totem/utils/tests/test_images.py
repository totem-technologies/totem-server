import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageCms

from totem.users.models import User
from totem.utils.images import ConvertToSRGB

FIXTURES = Path(__file__).parent / "fixtures"
P3_SWATCH = FIXTURES / "p3_swatch.png"  # solid (120, 220, 40) tagged with Display P3


def _srgb_reference(path: Path) -> tuple[int, int, int]:
    """Convert the fixture's embedded P3 profile to sRGB the canonical way."""
    img = Image.open(path)
    src = ImageCms.ImageCmsProfile(io.BytesIO(img.info["icc_profile"]))
    dst = ImageCms.createProfile("sRGB")
    return ImageCms.profileToProfile(img, src, dst, outputMode="RGB").getpixel((0, 0))[:3]


def test_convert_to_srgb_bakes_profile_into_pixels():
    img = Image.open(P3_SWATCH)
    raw = img.convert("RGB").getpixel((0, 0))[:3]
    expected = _srgb_reference(P3_SWATCH)
    assert expected != raw  # the fixture must actually be wide-gamut

    result = ConvertToSRGB().process(img)

    # Profile is baked into the pixels and the now-redundant tag is stripped.
    assert "icc_profile" not in result.info
    assert result.getpixel((0, 0))[:3] == expected


def test_convert_to_srgb_passes_through_untagged_images():
    img = Image.new("RGB", (4, 4), (10, 20, 30))
    result = ConvertToSRGB().process(img)
    assert result is img  # untouched, no profile to convert


def test_convert_to_srgb_survives_broken_profile():
    """A corrupt/truncated ICC profile must not crash the upload (raises OSError, not PyCMSError)."""
    img = Image.new("RGB", (4, 4), (120, 220, 40))
    img.info["icc_profile"] = b"this is not a valid icc profile"
    result = ConvertToSRGB().process(img)
    assert result.mode == "RGB"
    assert "icc_profile" not in result.info


def test_convert_to_srgb_preserves_alpha():
    """An image with alpha and an embedded profile keeps its alpha channel."""
    icc = Image.open(P3_SWATCH).info["icc_profile"]
    img = Image.new("RGBA", (4, 4), (120, 220, 40, 128))
    img.info["icc_profile"] = icc
    result = ConvertToSRGB().process(img)
    assert result.mode == "RGBA"
    assert result.getpixel((0, 0))[3] == 128
    assert "icc_profile" not in result.info


def test_convert_to_srgb_palette_mode_falls_back():
    """A paletted ('P') image can't be color-transformed; it falls back without crashing."""
    icc = Image.open(P3_SWATCH).info["icc_profile"]
    img = Image.new("P", (4, 4))
    img.info["icc_profile"] = icc
    result = ConvertToSRGB().process(img)
    assert result.mode in ("RGB", "RGBA")
    assert "icc_profile" not in result.info


@pytest.mark.django_db
def test_profile_image_bakes_in_p3_profile(user: User):
    """The full profile-image spec should color-manage a P3 upload into sRGB."""
    raw_bytes = P3_SWATCH.read_bytes()
    expected = _srgb_reference(P3_SWATCH)

    user.profile_image.save("p3.png", SimpleUploadedFile("p3.png", raw_bytes, "image/png"))
    user.refresh_from_db()

    with user.profile_image.open("rb") as fh:
        processed = Image.open(fh).convert("RGB")

    assert "icc_profile" not in processed.info
    # WEBP at q80 adds a little noise; allow a small tolerance per channel.
    px = processed.getpixel((10, 10))[:3]
    assert all(abs(a - b) <= 6 for a, b in zip(px, expected)), f"{px} != {expected}"


@pytest.mark.django_db
def test_profile_image_bakes_orientation_and_p3_together(user: User):
    """A single upload carrying BOTH EXIF orientation and a P3 profile is fully corrected.

    Guards the processor order: neither Transpose nor ConvertToSRGB may strip the
    metadata the other depends on.
    """
    icc = Image.open(P3_SWATCH).info["icc_profile"]
    img = Image.new("RGB", (100, 100))
    img.paste((255, 0, 0), (0, 0, 50, 50))  # top-left: red (raw, unrotated)
    img.paste((0, 255, 0), (50, 0, 100, 50))
    img.paste((0, 0, 255), (0, 50, 50, 100))
    img.paste((255, 255, 0), (50, 50, 100, 100))
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise to display
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif, icc_profile=icc)
    raw = buf.getvalue()

    user.profile_image.save("both.jpg", SimpleUploadedFile("both.jpg", raw, "image/jpeg"))
    user.refresh_from_db()
    with user.profile_image.open("rb") as fh:
        processed = Image.open(fh).convert("RGB").resize((100, 100))

    # Orientation applied: the top-left quadrant is no longer the raw red.
    r, g, b = processed.getpixel((25, 25))
    assert b > 128 and r < 128, f"orientation not baked: {(r, g, b)}"
    # Color managed: profile baked into pixels and stripped.
    assert "icc_profile" not in processed.info
