"""Public progress spinner environment check entrypoint."""

from __future__ import annotations

import os


def progress_spinners_disabled() -> bool:
    """Return True when transient spinners are disabled via the environment."""

    value: str | None = os.environ.get("SQLBUILD_NO_PROGRESS")
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}
