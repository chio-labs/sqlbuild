"""Render a typed cursor scalar."""

from sqlbuild.cursor_algebra._helpers.parsing import render_scalar
from sqlbuild.cursor_algebra.types import CursorScalar


def render(*, value: CursorScalar) -> str:
    """Render a scalar in the existing cursor output format."""

    return render_scalar(value=value)
