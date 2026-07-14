"""Encode text for storage in virtual state rows."""

from __future__ import annotations

from sqlbuild.virtual.state.helpers.encoding import encode_state_text_impl


def encode_state_text(value: str) -> str:
    """Encode text for storage in state rows."""

    return encode_state_text_impl(value)
