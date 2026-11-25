import pytest
from ninja.errors import ValidationError

from totem.notifications.validators import validate_fid


@pytest.mark.parametrize("fid", ["short", "a" * 512, "abc+/=é"])
def test_valid_fid(fid: str) -> None:
    assert validate_fid(fid) is True


@pytest.mark.parametrize("fid", ["", "a" * 513, "a b", "a\tb", "a\n", "a\u00a0b", "a\x00b", "a\x7fb", "a\x80b"])
def test_invalid_fid(fid: str) -> None:
    with pytest.raises(ValidationError, match="INVALID_FID"):
        validate_fid(fid)
