"""dbt interop exceptions."""

from __future__ import annotations

from sqlbuild._native import DbtInteropConfigError


class DbtProfileError(DbtInteropConfigError):
    """Raised when a dbt profile cannot be resolved for SQLBuild."""

    code: str = "C242"
