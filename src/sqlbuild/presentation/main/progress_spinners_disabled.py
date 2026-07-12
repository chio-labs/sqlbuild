"""Public progress spinner environment check entry."""

from __future__ import annotations

from sqlbuild.presentation.helpers.progress import (
    progress_spinners_disabled as _progress_spinners_disabled,
)


def progress_spinners_disabled() -> bool:
    """Return whether transient spinners are disabled via the environment."""

    return _progress_spinners_disabled()
