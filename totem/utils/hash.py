import hashlib
import hmac as _hmac
import uuid

from django.conf import settings


def basic_hash(data: str, as_int: bool = False) -> str | int:
    """Small hash that looks good in URLs. May not be 'safe' to use in all cases."""
    h = hashlib.blake2b(data.encode("utf-8"), digest_size=10).hexdigest()
    if as_int:
        return int(h, 16)
    return h


def hmac(data: str, key: str = settings.SECRET_KEY) -> str:
    """Returns a HMAC-SHA256 hash of the data using the key."""
    return _hmac.new(key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def random_password() -> str:
    return str(basic_hash(uuid.uuid4().hex))
