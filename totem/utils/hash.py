import hashlib


def basic_hash(data: str):
    """Small hash that should not be used for anything serious. Looks good though."""
    return hashlib.blake2b(data.encode("utf-8"), digest_size=10).hexdigest()
