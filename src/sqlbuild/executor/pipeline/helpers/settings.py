"""Executor pipeline settings resolution."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.shared.types import TablePromotionMode
from sqlbuild.spec.models.project import SettingsConfig


def resolve_promotion_mode(
    *,
    settings: SettingsConfig,
    adapter: BaseAdapter,
) -> TablePromotionMode:
    """Resolve the effective table promotion mode from project settings or adapter default."""

    if settings.table_promotion_mode is not None:
        return TablePromotionMode(settings.table_promotion_mode)
    return TablePromotionMode(adapter.default_table_promotion_mode())
