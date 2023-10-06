import hashlib
import hmac as _hmac

from django.conf import settings


def basic_hash(data: str, as_int: bool = False) -> str | int:
    """Small hash that should not be used for anything serious. Looks good though."""
    h = hashlib.blake2b(data.encode("utf-8"), digest_size=10).hexdigest()
    if as_int:
        return int(h, 16)
    return h


def hmac(data: str, key: str) -> str:
    """Returns a HMAC-SHA256 hash of the data using the key."""
    key = key or settings.SECRET_KEY
    return _hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()
