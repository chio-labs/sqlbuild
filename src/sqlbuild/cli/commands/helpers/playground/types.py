"""Playground command type-layer declarations."""

from __future__ import annotations

from enum import StrEnum


class PlaygroundTemplate(StrEnum):
    """Available `sqb playground` templates."""

    WAFFLE_SHOP = "waffle_shop"
    LOADER_WAFFLE_SHOP = "loader_waffle_shop"
    DAGSTER = "dagster"
    RIVERS = "rivers"
    VIRTUAL = "virtual"
    PYTHON_NODES = "python_nodes"
    DBT = "dbt"
