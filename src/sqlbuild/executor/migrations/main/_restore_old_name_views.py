"""Re-create released compatibility views after a failed build."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.migrations._helpers.old_name_views import refresh_old_name_views
from sqlbuild.executor.migrations.models import OldNameViewSource


def restore_old_name_views(
    *, adapter: BaseAdapter, connection: Any, sources: tuple[OldNameViewSource, ...]
) -> None:
    """Re-create compatibility views in dependency order against current columns."""

    _ = refresh_old_name_views(adapter=adapter, connection=connection, sources=sources)
