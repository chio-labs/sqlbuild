from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import EnvironmentConfig, LocalConfig, ProjectConfig
from tests.unit.src.sqlbuild.cli.commands.main.shared.helpers._test_types import (
    ResolveProjectConnectionConfigTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        ResolveProjectConnectionConfigTestCase(
            description="uses project environment and local connection precedence",
            project_dir_name="demo_project",
            expected_connection={
                "database": "demo_project/local.duckdb",
                "warehouse": "dev_wh",
                "role": "local_role",
            },
        )
    ],
    ids=["uses project environment and local connection precedence"],
)
def test_given_project_inputs_when_resolving_connection_then_uses_effective_connection(
    test_case: ResolveProjectConnectionConfigTestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = tmp_path / test_case.project_dir_name
    project_dir.mkdir()
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            default_environment="dev",
            connection={"database": "project.duckdb", "warehouse": "project_wh"},
            environments={
                "dev": EnvironmentConfig(
                    connection={"database": "dev.duckdb", "warehouse": "dev_wh"}
                )
            },
        ),
        local_config=LocalConfig(connection={"database": "local.duckdb", "role": "local_role"}),
    )

    connection: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=project_dir,
    )

    assert connection == {
        key: (
            str(tmp_path / value)
            if key == "database" and isinstance(value, str) and not value.startswith("/")
            else value
        )
        for key, value in test_case.expected_connection.items()
    }
