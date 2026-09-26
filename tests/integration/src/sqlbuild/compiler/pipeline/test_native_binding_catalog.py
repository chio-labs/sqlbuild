"""Native catalog semantics through the compiler and physical rebinding path."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile.main._source_bindings import get_source_binding_diagnostics
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import NativeCatalogCase


@pytest.mark.parametrize(
    "test_case",
    [
        NativeCatalogCase("derived alias", 'SELECT "orderid" FROM (SELECT 1 AS "OrderId") q'),
        NativeCatalogCase(
            "CTE and alias",
            'WITH "OrderValues" AS (SELECT 1 AS "OrderId") SELECT "orderid" FROM "ordervalues"',
        ),
        NativeCatalogCase(
            "binding preserves type checks",
            'SELECT SUM("active") FROM (SELECT TRUE AS "Active") q',
            ("B213",),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_quoted_case_semantics_when_compiling_then_resolves_native_aliases(
    test_case: NativeCatalogCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n[rules]\nselect = []\n[connection]\nsession_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = true }\n'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models/orders.sql").write_text(
        "MODEL (database warehouse, schema analytics);\n" + test_case.sql
    )
    main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"])
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in payload["diagnostics"]) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        NativeCatalogCase(
            "authored quoted typo", 'SELECT "MiSsPeLlEd" FROM (SELECT 1 AS "OrderId") q', ("B002",)
        ),
        NativeCatalogCase(
            "uppercase quoted typo",
            'SELECT "MISSPELLED" FROM (SELECT 1 AS "OrderId") q',
            ("B002",),
            "MISSPELLED",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_quoted_typo_when_validating_then_keeps_authored_spelling_and_span(
    test_case: NativeCatalogCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n[rules]\nselect = []\n[connection]\nsession_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = true }\n'
    )
    (tmp_path / "models").mkdir()
    sql: str = "MODEL (database warehouse, schema analytics);\n" + test_case.sql
    (tmp_path / "models/orders.sql").write_text(sql)
    assert main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"]) == 1
    payload: dict[str, Any] = json.loads(capsys.readouterr().out)
    (diagnostic,) = payload["diagnostics"]
    assert (diagnostic["code"],) == test_case.expected_codes
    assert test_case.spelling in diagnostic["message"]
    assert diagnostic["line"] == 2
    assert f'"{test_case.spelling}"' in payload["resources"]["models"][0]["query_sql"]


@pytest.mark.parametrize(
    "test_case",
    [
        NativeCatalogCase(
            "physical schema refresh", 'SELECT "orderid" FROM __source("orders")', ("B002",)
        )
    ],
    ids=lambda case: case.description,
)
def test_given_catalog_when_rebinding_physical_shapes_then_does_not_reuse_stale_columns(
    test_case: NativeCatalogCase, tmp_path: Path
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n[rules]\nselect = []\n[connection]\nsession_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = true }\n'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "sources").mkdir()
    (tmp_path / "sources/orders.yml").write_text("sources:\n  - name: orders\n    table: orders\n")
    (tmp_path / "models/report.sql").write_text(
        "MODEL (database warehouse, schema analytics);\n" + test_case.sql
    )
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discover_project_inputs(project_dir=tmp_path), adapter=SnowflakeAdapter()
    )
    assert project.binding_catalog is not None
    keys: frozenset[CompiledObjectKey] = frozenset(model.key for model in project.models)
    profile: ExpressionInferenceProfile = ExpressionInferenceProfile(
        sql_analysis_dialect="snowflake"
    )
    missing: tuple[CompilerDiagnostic, ...] = get_source_binding_diagnostics(
        project=project,
        columns={"orders": (ColumnInfo("customer", "VARCHAR"),)},
        profile=profile,
        selected_keys=keys,
    )
    present: tuple[CompilerDiagnostic, ...] = get_source_binding_diagnostics(
        project=project,
        columns={"orders": (ColumnInfo("OrderId", "INTEGER"),)},
        profile=profile,
        selected_keys=keys,
    )
    repeated: tuple[CompilerDiagnostic, ...] = get_source_binding_diagnostics(
        project=project,
        columns={"orders": (ColumnInfo("customer", "VARCHAR"),)},
        profile=profile,
        selected_keys=keys,
    )
    assert tuple(item.code for item in missing) == test_case.expected_codes
    assert present == ()
    assert repeated == missing


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
