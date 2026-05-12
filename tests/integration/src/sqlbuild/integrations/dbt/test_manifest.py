from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.compile.main.build_compile_inputs import build_compile_inputs
from sqlbuild.compiler.compile.models import CompileProjectInputs
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt.helpers.runner import DbtRunner
from sqlbuild.integrations.dbt.models import DbtCliOptions, DbtCommandResult
from tests.integration.src.sqlbuild.integrations.dbt._test_types import (
    RealDbtManifestCompileTestCase,
)
from tests.integration.src.sqlbuild.integrations.dbt.helpers import attach_dbt_manifest_file

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        RealDbtManifestCompileTestCase(
            description="resolves SQLBuild dbt ref from real dbt manifest",
            sqlbuild_model_sql='MODEL ();\n\nselect order_id from __dbt_ref("stg_orders")\n',
            expected_compiled_sql='select order_id from "memory"."main"."stg_orders"',
        ),
    ],
    ids=["resolves SQLBuild dbt ref from real dbt manifest"],
)
def test_given_real_dbt_manifest_when_compiling_sqlbuild_then_resolves_dbt_ref(
    test_case: RealDbtManifestCompileTestCase,
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

    sqlbuild_project_dir: Path = tmp_path / "sqlbuild_project"
    sqlbuild_project_dir.joinpath("models").mkdir(parents=True)
    sqlbuild_project_dir.joinpath("target").mkdir()
    sqlbuild_project_dir.joinpath("sqlbuild_project.toml").write_text(
        'name = "demo"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    sqlbuild_project_dir.joinpath("models/downstream_orders.sql").write_text(
        test_case.sqlbuild_model_sql, encoding="utf-8"
    )
    sqlbuild_project_dir.joinpath("target/manifest.json").write_text(
        dbt_project_dir.joinpath("target/manifest.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    discovered_inputs: DiscoveredProjectInputs = attach_dbt_manifest_file(
        discovered_inputs=discover_project_inputs(project_dir=sqlbuild_project_dir),
        manifest_source=dbt_project_dir / "target/manifest.json",
    )
    compile_inputs: CompileProjectInputs = build_compile_inputs(discovered_inputs)

    assert compile_inputs.model_inputs[0].query_sql == test_case.expected_compiled_sql
