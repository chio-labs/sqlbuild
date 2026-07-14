"""Decode text stored in virtual state rows."""

from __future__ import annotations

from sqlbuild.virtual.state._helpers.encoding import decode_state_text_impl


def decode_state_text(value: str | None) -> str | None:
    """Decode text stored in state rows."""

    return decode_state_text_impl(value)
