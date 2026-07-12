from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.compiler.compile.helpers.assembly.project import assemble_compiled_project
from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models.core import (
    CompiledProject,
    CompileProjectInputs,
)
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.cli.runner import DbtRunner
from sqlbuild.integrations.dbt.helpers.graph.core import (
    build_dbt_combined_graph,
    dbt_model_graph_key,
    expand_combined_downstream,
)
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from sqlbuild.integrations.dbt.models import (
    DbtCliOptions,
    DbtCombinedGraph,
    DbtCommandResult,
)
from tests.integration.src.sqlbuild.integrations.dbt._test_types import (
    RealDbtCombinedGraphTestCase,
)
from tests.integration.src.sqlbuild.integrations.dbt.helpers import (
    build_external_sql_reference_resolver,
    build_sqlbuild_project_with_manifest,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import graph_key_stable_ids

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtCombinedGraphTestCase(
            description="expands from real dbt model to downstream SQLBuild models",
            sqlbuild_model_sql_by_name={
                "downstream_orders": 'select order_id from __dbt_ref("fact_orders")',
                "mart_orders": 'select order_id from __ref("downstream_orders")',
            },
            expected_downstream_from="model.analytics.fact_orders",
            expected_downstream_keys=("sqb:model:downstream_orders", "sqb:model:mart_orders"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_real_dbt_manifest_and_sqlbuild_project_when_building_graph_then_expands_downstream(
    test_case: RealDbtCombinedGraphTestCase,
    real_dbt_executable: str,
    dbt_project_dir: Path,
    dbt_profiles_dir: Path,
    tmp_path: Path,
) -> None:
    options: DbtCliOptions = DbtCliOptions(
        project_dir=dbt_project_dir,
        profiles_dir=dbt_profiles_dir,
        target_path=dbt_project_dir / "target",
    )
    compile_result: DbtCommandResult = DbtRunner(dbt_executable=real_dbt_executable).compile(
        options=options
    )
    assert compile_result.returncode == 0, compile_result.stderr or compile_result.stdout

    sqlbuild_project_dir: Path = build_sqlbuild_project_with_manifest(
        tmp_path=tmp_path,
        manifest_source=dbt_project_dir / "target/manifest.json",
        model_sql_by_name=test_case.sqlbuild_model_sql_by_name,
    )
    manifest_source: Path = dbt_project_dir / "target/manifest.json"
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=sqlbuild_project_dir
    )
    compile_inputs: CompileProjectInputs = build_compile_inputs(
        discovered_inputs=discovered_inputs,
        external_sql_reference_resolver=build_external_sql_reference_resolver(
            manifest_source=manifest_source
        ),
    )
    project: CompiledProject = assemble_compiled_project(inputs=compile_inputs)
    manifest: DbtManifestIndex = build_dbt_manifest_index(
        raw_data=json.loads(manifest_source.read_text(encoding="utf-8"))
    )

    graph: DbtCombinedGraph = build_dbt_combined_graph(manifest=manifest, project=project)

    assert (
        graph_key_stable_ids(
            expand_combined_downstream(
                key=dbt_model_graph_key(test_case.expected_downstream_from),
                downstream=graph.downstream_deps,
            )
        )
        == test_case.expected_downstream_keys
    )
