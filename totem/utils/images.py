import io

from PIL import Image, ImageCms

# Browsers assume an image with no embedded ICC profile is sRGB. Phone cameras
# (notably iPhones) tag photos with a wide-gamut Display P3 profile, which we drop
# when re-encoding to WEBP. Without color management the wide-gamut pixels get
# reinterpreted as sRGB and look washed out, so we bake the profile into sRGB pixels.
_SRGB_PROFILE = ImageCms.createProfile("sRGB")


class ConvertToSRGB:
    """Imagekit/pilkit processor that bakes an embedded ICC profile into sRGB pixels.

    Images without an ICC profile are passed through unchanged. The (now redundant)
    profile is stripped from the result so the saved file carries plain sRGB pixels.
    """

    def process(self, img: Image.Image) -> Image.Image:
        icc = img.info.get("icc_profile")
        if not icc:
            return img

        # Preserve an alpha channel (e.g. transparent PNG logos) through the conversion.
        out_mode = "RGBA" if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info else "RGB"
        try:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            converted = ImageCms.profileToProfile(img, source_profile, _SRGB_PROFILE, outputMode=out_mode)
        except (ImageCms.PyCMSError, OSError):
            # Unreadable/corrupt profile (OSError) or unsupported mode (PyCMSError):
            # fall back to a plain mode coercion rather than failing the upload.
            converted = img.convert(out_mode)

        # profileToProfile may return None on failure; never break the upload.
        if converted is None:
            return img.convert(out_mode)

        converted.info.pop("icc_profile", None)
        return converted
