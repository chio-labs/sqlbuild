"""Shared selector expansion marker parsing."""

from __future__ import annotations

from sqlbuild.shared.exceptions.errors import SharedInputError
from sqlbuild.shared.models import SelectorExpansion


def split_selector_expansion(raw: str) -> SelectorExpansion:
    """Split +selector+ marker syntax from the selector core without resolving the core."""

    stripped: str = raw.strip()
    if not stripped:
        raise SharedInputError("empty selector")
    upstream: bool = stripped.startswith("+")
    downstream: bool = stripped.endswith("+")
    core: str = stripped.lstrip("+").rstrip("+")
    if not core:
        raise SharedInputError(f"selector '{stripped}' has no name after removing '+' markers")
    if "+" in core:
        raise SharedInputError(f"selector '{stripped}' contains '+' in an unsupported position")
    return SelectorExpansion(core=core, upstream=upstream, downstream=downstream)
