"""Lazy Rivers imports for the optional integration."""

from __future__ import annotations

from typing import Any

from sqlbuild.integrations.rivers.exceptions import RiversDependencyError


def load_rivers() -> Any:
    """Import Rivers or raise an actionable optional-dependency error."""

    try:
        import rivers as rs
    except ModuleNotFoundError as error:
        raise RiversDependencyError(
            "Rivers is required for sqlbuild.integrations.rivers. "
            "Install SQLBuild with the rivers extra, e.g. `pip install sqlbuild[rivers]`."
        ) from error
    return rs
