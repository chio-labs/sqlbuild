"""Public check for whether a project's adapter selects a session warehouse."""

from __future__ import annotations

from pathlib import Path


def adapter_supports_session_warehouse(*, adapter_name: str, project_dir: Path | None) -> bool:
    """Return whether the adapter, resolved like any project adapter, has a session warehouse."""

    from sqlbuild.adapter.discovery.main.resolve_adapter import resolve_adapter

    return resolve_adapter(
        adapter_name=adapter_name, project_dir=project_dir
    ).supports_session_warehouse
