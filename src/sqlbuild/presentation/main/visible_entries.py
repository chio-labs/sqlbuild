"""Public bounded-output visibility entry."""

from __future__ import annotations

from collections.abc import Sequence

from sqlbuild.presentation.helpers.display import visible_entries as _visible_entries
from sqlbuild.presentation.models import DisplayOptions


def visible_entries[T](*, entries: Sequence[T], options: DisplayOptions) -> Sequence[T]:
    """Return entries visible under the current display cap."""

    return _visible_entries(entries=entries, options=options)
