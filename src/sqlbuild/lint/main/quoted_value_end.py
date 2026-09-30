"""Public end-offset finder for quoted MODEL header values."""

from __future__ import annotations

from sqlbuild.lint._helpers.native import quoted_value_end as _quoted_value_end


def quoted_value_end(*, text: str, start: int) -> int:
    """Return the offset just past the quoted value that opens at start."""

    return _quoted_value_end(text=text, start=start)
