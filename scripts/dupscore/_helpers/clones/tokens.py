"""Build clone units from lexed token streams."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from scripts.dupscore.models import CloneUnit

_KEY_SEPARATOR: str = "\x1f"
_DIGEST_BYTES: int = 16


def build_clone_unit(
    *,
    language: str,
    path: str,
    name: str,
    start_line: int,
    end_line: int,
    normalized: list[str],
    concrete: list[str],
) -> CloneUnit:
    """Assemble a unit with identity keys for its concrete and normalised streams."""

    return CloneUnit(
        language=language,
        path=path,
        name=name,
        start_line=start_line,
        end_line=end_line,
        normalized=tuple(normalized),
        concrete_key=_digest(concrete),
        normalized_key=_digest(normalized),
    )


def _digest(parts: Iterable[str]) -> str:
    joined: str = _KEY_SEPARATOR.join(parts)
    return hashlib.blake2b(joined.encode("utf-8"), digest_size=_DIGEST_BYTES).hexdigest()
