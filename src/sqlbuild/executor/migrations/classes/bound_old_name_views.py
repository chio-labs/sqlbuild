"""Compatibility views bound to one model's relation during a build that replaces or alters it."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.executor.migrations._helpers.old_name_views import (
    present_old_name_views,
    rebind_old_name_views,
    recreate_old_name_views,
    release_old_name_views,
)
from sqlbuild.executor.migrations.models import OldNameViewSource


class BoundOldNameViews:
    """Views released before column changes are re-created with the privileges they had."""

    def __init__(
        self, *, adapter: BaseAdapter, connection: Any, sources: tuple[OldNameViewSource, ...]
    ) -> None:
        self._adapter: BaseAdapter = adapter
        self._connection: Any = connection
        self._sources: tuple[OldNameViewSource, ...] = sources
        self._released: tuple[OldNameViewSource, ...] = ()

    def release(self) -> int:
        """Capture privileges of the views that exist, then drop them."""

        self._released = release_old_name_views(
            adapter=self._adapter,
            connection=self._connection,
            sources=present_old_name_views(
                adapter=self._adapter, connection=self._connection, sources=self._sources
            ),
        )
        return len(self._released)

    def rebind(self) -> int:
        """Re-create released views, or point existing ones at the relation's new columns."""

        released: tuple[OldNameViewSource, ...] = self._released
        self._released = ()
        if released:
            return recreate_old_name_views(
                adapter=self._adapter, connection=self._connection, sources=released
            )
        return rebind_old_name_views(
            adapter=self._adapter, connection=self._connection, sources=self._sources
        )
