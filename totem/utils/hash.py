import hashlib


def basic_hash(data: str, as_int: bool = False) -> str | int:
    """Small hash that should not be used for anything serious. Looks good though."""
    h = hashlib.blake2b(data.encode("utf-8"), digest_size=10).hexdigest()
    if as_int:
        return int(h, 16)
    return h
