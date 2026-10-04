"""Shared builders for command-group warehouse resolution tests."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    TargetConfig,
    TargetWarehousesConfig,
)
from tests.unit.src.sqlbuild.cli.commands._helpers.runtime._test_types import (
    CommandWarehouseResolutionTestCase,
)


def build_warehouse_discovered_inputs(
    test_case: CommandWarehouseResolutionTestCase,
) -> DiscoveredProjectInputs:
    """Build a `dev`/`prod` project whose `dev` target uses the case's warehouse groups."""

    return DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="shop",
            adapter=test_case.adapter,
            default_target="dev",
            connections={"main": dict(test_case.connection)},
            targets={
                "dev": TargetConfig(
                    connection_name="main", warehouses=test_case.project_warehouses
                ),
                "prod": TargetConfig(
                    connection_name="main",
                    warehouses=TargetWarehousesConfig(build="PROD_BUILD_WH"),
                ),
            },
        ),
        local_config=LocalConfig(
            adapter=test_case.local_adapter, targets=dict(test_case.local_targets)
        ),
    )


def write_case_adapter_file(*, project_dir: Path, contents: str) -> None:
    """Write the case's project-local adapter module, which may be empty."""

    (project_dir / "adapters").mkdir(exist_ok=True)
    (project_dir / "adapters" / "custom.py").write_text(contents, encoding="utf-8")
