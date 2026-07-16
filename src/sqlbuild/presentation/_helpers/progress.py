"""Progress environment implementations."""

from __future__ import annotations

import os

from sqlbuild.presentation.constants import PROGRESS_DISABLED_VALUES


def progress_spinners_disabled() -> bool:
    value: str | None = os.environ.get("SQLBUILD_NO_PROGRESS")
    return value is not None and value.strip().lower() in PROGRESS_DISABLED_VALUES
