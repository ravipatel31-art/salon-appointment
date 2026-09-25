"""India mobile normalization for guest checkout (CONTRACT §Bookings).

Accepted input: 10 digits, or 10 digits after an optional ``+91`` / ``0`` /
``91`` prefix (spaces, dashes and parentheses ignored).
Stored form: the bare 10-digit number.
"""

from __future__ import annotations


def normalize_india_mobile(raw: str | None) -> str | None:
    """Return the 10-digit Indian mobile for `raw`, or None if invalid."""
    if not raw:
        return None
    s = (
        raw.strip()
        .replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
    )
    if s.startswith("+91"):
        s = s[3:]
    elif s.startswith("0091"):
        s = s[4:]
    if len(s) == 11 and s.startswith("0"):
        s = s[1:]
    elif len(s) == 12 and s.startswith("91"):
        s = s[2:]
    if len(s) == 10 and s.isdigit():
        return s
    return None
