"""Compare normalized project-relative path components."""

from __future__ import annotations

from pathlib import PurePath

from sqlbuild.compiler.scopes._helpers.paths import is_equal_or_descendant


def path_is_equal_or_descendant(*, path: str | PurePath, ancestor: str | PurePath) -> bool:
    """Compare normalized path components rather than textual prefixes."""

    return is_equal_or_descendant(path=path, ancestor=ancestor)
