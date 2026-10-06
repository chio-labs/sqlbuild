"""Shared builders for diff CLI helper unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from sqlbuild.cli.commands.models import DiffCommandRequest
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.executor.diff.models import FullDiffModelSize, FullDiffSideSize
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    TargetConfig,
    TargetDiffConfig,
)


def diff_request(
    *,
    full: bool = False,
    schema_only: bool = False,
    bounded: str | None = None,
    select: tuple[str, ...] = ("orders",),
    unique_key_override: tuple[str, ...] = (),
    project_dir: Path | None = None,
) -> DiffCommandRequest:
    """Return a model diff request from prod with the TO target left to the default."""

    return DiffCommandRequest(
        project_dir=project_dir,
        no_color=True,
        no_sql_validation=False,
        from_name="prod",
        to_name=None,
        full=full,
        schema_only=schema_only,
        bounded=bounded,
        select=select,
        unique_key_override=unique_key_override,
    )


def prod_dev_inputs(
    *,
    prod_max_full_rows: int | Literal["unlimited"] | None,
    dev_max_full_rows: int | Literal["unlimited"] | None,
) -> DiscoveredProjectInputs:
    """Return discovered inputs with prod and dev targets carrying the given diff limits."""

    return DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="shop",
            adapter="duckdb",
            targets={
                "prod": TargetConfig(
                    schema="prod", diff=TargetDiffConfig(max_full_rows=prod_max_full_rows)
                ),
                "dev": TargetConfig(
                    schema="dev", diff=TargetDiffConfig(max_full_rows=dev_max_full_rows)
                ),
            },
        ),
        local_config=LocalConfig(),
    )


def blocked_orders(*, has_cursor: bool) -> tuple[FullDiffModelSize, ...]:
    """Return one blocked model: prod over its limit and dev a view of unknown size."""

    return (
        FullDiffModelSize(
            name="orders",
            left=FullDiffSideSize(
                target="prod", relation="prod.orders", row_count=12_500_000, max_rows=10_000_000
            ),
            right=FullDiffSideSize(
                target="dev",
                relation="dev.orders",
                row_count=None,
                max_rows=10_000_000,
                detail="no row count (view)",
            ),
            has_cursor=has_cursor,
        ),
    )
