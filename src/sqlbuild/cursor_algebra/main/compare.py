"""Compare typed cursor scalars."""

from sqlbuild.cursor_algebra._helpers.comparison import compare_scalars
from sqlbuild.cursor_algebra.types import CursorScalar


def compare(*, left: CursorScalar, right: CursorScalar) -> int:
    """Compare compatible cursor scalar values."""

    return compare_scalars(left=left, right=right)
