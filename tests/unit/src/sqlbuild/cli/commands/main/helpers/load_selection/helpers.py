"""Helpers for load-selection unit tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import (
    DiscoveredLoaderFunction,
    DiscoveredProjectInputs,
    DiscoveredSourceFile,
)
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig
from sqlbuild.spec.models.source import SourceEntry


def fetch_orders(_ctx: object) -> list[dict[str, object]]:
    return []


def raw_orders(_ctx: object) -> list[dict[str, object]]:
    return []


def load_raw_orders(_ctx: object) -> list[dict[str, object]]:
    return []


def build_load_selection_inputs() -> DiscoveredProjectInputs:
    """Build inputs with a source name that collides with an unrelated loader name."""

    return DiscoveredProjectInputs(
        project_config=ProjectConfig(name="demo", adapter="duckdb"),
        local_config=LocalConfig(),
        source_files=(
            DiscoveredSourceFile(
                file_path=Path("sources/raw.yml"),
                relative_path=Path("sources/raw.yml"),
                contents="",
                source_entries=(SourceEntry(name="raw_orders", loader="load_raw_orders"),),
            ),
        ),
        loader_functions=(
            DiscoveredLoaderFunction(
                file_path=Path("loaders/loaders.py"),
                relative_path=Path("loaders/loaders.py"),
                name="fetch_orders",
                function=fetch_orders,
            ),
            DiscoveredLoaderFunction(
                file_path=Path("loaders/loaders.py"),
                relative_path=Path("loaders/loaders.py"),
                name="raw_orders",
                function=raw_orders,
            ),
            DiscoveredLoaderFunction(
                file_path=Path("loaders/loaders.py"),
                relative_path=Path("loaders/loaders.py"),
                name="load_raw_orders",
                function=load_raw_orders,
                depends_on=(fetch_orders,),
            ),
        ),
    )
