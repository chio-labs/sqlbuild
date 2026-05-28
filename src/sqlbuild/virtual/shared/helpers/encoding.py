"""Encoding helpers for portable virtual state text payloads."""

from __future__ import annotations

import base64


def encode_state_text(value: str) -> str:
    """Encode text for storage in state rows."""

    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def decode_state_text(value: str | None) -> str | None:
    """Decode text stored in state rows."""

    if value is None:
        return None
    return base64.b64decode(value.encode("ascii")).decode("utf-8")
