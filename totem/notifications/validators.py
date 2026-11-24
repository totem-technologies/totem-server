import unicodedata

from ninja.errors import ValidationError


def validate_fid(fid: str) -> bool:
    if not fid or len(fid) > 512 or any(c.isspace() or unicodedata.category(c) == "Cc" for c in fid):
        raise ValidationError(errors=[{"fid": "INVALID_FID"}])
    return True
