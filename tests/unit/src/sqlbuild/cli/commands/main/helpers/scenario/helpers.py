from pathlib import Path

from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlScenario,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.discovery.models import DiscoveredSqlScenarioFile


def build_project_with_scenarios(project_dir: Path) -> CompiledProject:
    scenarios: tuple[CompiledSqlScenario, ...] = tuple(
        CompiledSqlScenario(
            key=CompiledObjectKey(CompiledResourceType.SQL_SCENARIO, scenario_name),
            name=scenario_name,
            scenario_file=DiscoveredSqlScenarioFile(
                file_path=project_dir / relative_path,
                relative_path=Path(relative_path),
                contents="SCENARIO();\n\nSELECT 1\n",
                header_values={},
                sql_body="SELECT 1",
                name=scenario_name,
            ),
            sql_body="SELECT 1",
        )
        for scenario_name, relative_path in (
            ("orders_paid", "tests/scenarios/orders/paid.sql"),
            ("orders_refund", "tests/scenarios/orders/refund.sql"),
        )
    )
    return CompiledProject(
        run_id="test_run",
        effective_environment_name=None,
        effective_connection={},
        effective_vars={},
        sql_scenarios=scenarios,
    )
