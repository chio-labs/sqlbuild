"""Scenario dialect helpers."""

from __future__ import annotations

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.cli.commands.constants import (
    SCENARIO_CLI_CAPTURE_DIALECT_REQUIRED,
)
from sqlbuild.cli.commands.exceptions import CliUserError


def require_scenario_capture_dialect(*, adapter: BaseAdapter, adapter_name: str) -> str:
    """Return the SQL analysis dialect required for scenario snapshot compatibility."""

    dialect: str | None = adapter.sql_analysis_dialect()
    if dialect is None:
        raise CliUserError(
            f"Adapter '{adapter_name}' must define a SQL analysis dialect for scenario snapshots",
            code=SCENARIO_CLI_CAPTURE_DIALECT_REQUIRED,
            help=(
                "Set sql_analysis_dialect_name on the adapter so captured snapshots can be "
                "validated and replayed locally."
            ),
        )
    return dialect
