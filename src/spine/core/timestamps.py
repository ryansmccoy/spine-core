"""
ULID generation and timestamp utilities (stdlib-only).

Shared platform primitives for generating time-sortable unique IDs
and working with UTC timestamps. All spines should import from here
instead of maintaining their own copies.

STDLIB ONLY - NO PYDANTIC.
"""

import random
import time
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Get current UTC datetime."""
    return datetime.now(UTC)


def generate_ulid() -> str:
    """
    Generate a ULID-like identifier.

    Format: 26 characters, base32 encoded, time-sortable.
    This is a simplified implementation for stdlib-only usage.
    """
    # Time component: milliseconds since epoch (48 bits -> 10 chars)
    timestamp_ms = int(time.time() * 1000)
    timestamp_chars = _encode_base32(timestamp_ms, 10)

    # Random component (80 bits -> 16 chars)
    random_part = "".join(random.choices(_ENCODING, k=16))

    return timestamp_chars + random_part


def to_iso8601(dt: datetime | None) -> str | None:
    """Convert datetime to ISO 8601 string."""
    if dt is None:
        return None
    return dt.isoformat()


def from_iso8601(s: str | None) -> datetime | None:
    """Parse ISO 8601 string to datetime."""
    if s is None:
        return None
    return datetime.fromisoformat(s)


# ULID base32 alphabet (Crockford's)
_ENCODING = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ENCODING_LEN = len(_ENCODING)


def _encode_base32(value: int, length: int) -> str:
    """Encode integer to base32 string of fixed length."""
    result = []
    for _ in range(length):
        result.append(_ENCODING[value % _ENCODING_LEN])
        value //= _ENCODING_LEN
    return "".join(reversed(result))
