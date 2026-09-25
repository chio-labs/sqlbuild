"""Synthetic regressions for target semantics and error-local recovery."""

import json
from pathlib import Path
from typing import Any

import pytest

from sqlbuild.adapter.contract.models import ColumnInfo, ExpressionInferenceProfile
from sqlbuild.adapters.snowflake.classes.snowflake_adapter import SnowflakeAdapter
from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile.main._source_bindings import get_source_binding_diagnostics
from sqlbuild.compiler.compile.models import CompiledProject, CompilerDiagnostic
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.pipeline.main.compiled_project import build_compiled_project
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import SemanticTriageCase


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticTriageCase("date"),
        SemanticTriageCase("timestamp", column_type="TIMESTAMP"),
        SemanticTriageCase("timestamp ntz", column_type="TIMESTAMP_NTZ"),
        SemanticTriageCase("timestamp ltz", column_type="TIMESTAMP_LTZ"),
        SemanticTriageCase("timestamp tz", column_type="TIMESTAMP_TZ"),
        SemanticTriageCase("varchar incompatible", column_type="VARCHAR", expected_codes=("B301",)),
        SemanticTriageCase("number incompatible", column_type="NUMBER", expected_codes=("B301",)),
        SemanticTriageCase("boolean incompatible", column_type="BOOLEAN", expected_codes=("B301",)),
    ],
    ids=lambda case: case.description,
)
def test_given_cursor_families_when_compiling_then_accepts_temporal_pairs_only(
    test_case: SemanticTriageCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n[rules]\nselect = []\n'
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "sources/orders.yml").write_text(
        "sources:\n  - name: orders\n    table: orders\n    contract: enforced\n"
        f"    columns:\n      - name: ordered_at\n        type: {test_case.column_type}\n"
    )
    (tmp_path / "models/recent_orders.sql").write_text(
        "MODEL (materialized incremental, database warehouse, schema analytics, "
        f"incremental_strategy append, cursor ordered_at, cursor_type {test_case.cursor_type}, "
        'cursor_grain day);\nSELECT ordered_at FROM __source("orders")'
    )
    main(["--project-dir", str(tmp_path), "compile", "--no-cache", "--json"])
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in result["diagnostics"]) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticTriageCase(
            "enabled", setting="session_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = true }\n"
        ),
        SemanticTriageCase(
            "disabled",
            setting="session_parameters = { QUOTED_IDENTIFIERS_IGNORE_CASE = false }\n",
            expected_codes=("B002",),
        ),
        SemanticTriageCase("absent", expected_codes=("B002",)),
    ],
    ids=lambda case: case.description,
)
def test_given_effective_target_when_binding_quotes_then_honours_session_setting(
    test_case: SemanticTriageCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "snowflake"\n[rules]\nselect = []\n'
        '[targets.selected]\nschema = "preserve"\n[targets.selected.connection]\n'
        + test_case.setting
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "models").mkdir()
    (tmp_path / "sources/orders.yml").write_text(
        "sources:\n  - name: orders\n    table: orders\n    contract: enforced\n"
        "    columns:\n      - name: customer\n        type: VARCHAR\n"
    )
    (tmp_path / "models/quoted_orders.sql").write_text(
        "MODEL (materialized view, database warehouse, schema analytics);\n"
        'SELECT o."customer" FROM __source("orders") o'
    )
    for _ in range(2):
        main(["--project-dir", str(tmp_path), "compile", "--target", "selected", "--json"])
        result: dict[str, Any] = json.loads(capsys.readouterr().out)
        assert tuple(item["code"] for item in result["diagnostics"]) == test_case.expected_codes
    project: CompiledProject = build_compiled_project(
        discovered_inputs=discover_project_inputs(project_dir=tmp_path),
        adapter=SnowflakeAdapter(),
        selected_target="selected",
    )
    physical: tuple[CompilerDiagnostic, ...] = get_source_binding_diagnostics(
        project=project,
        columns={"orders": (ColumnInfo(name="customer", type="VARCHAR"),)},
        profile=ExpressionInferenceProfile(sql_analysis_dialect="snowflake"),
        selected_keys=frozenset(model.key for model in project.models),
    )
    assert tuple(item.code for item in physical) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticTriageCase("type cascade", expected_codes=("B212",)),
        SemanticTriageCase(
            "declared type cascade",
            root_contract=", contract enforced, columns (total (type INTEGER), ordered_at (type TIMESTAMP))",
            expected_codes=("B212",),
        ),
        SemanticTriageCase(
            "independent column remains checked",
            independent_sql=", missing",
            expected_codes=("B212", "B002"),
        ),
        SemanticTriageCase(
            "independent type error remains checked",
            independent_sql=", ordered_at + 1 AS independent",
            expected_codes=("B212", "B212"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_type_error_root_when_binding_dependants_then_recovers_only_poisoned_outputs(
    test_case: SemanticTriageCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "models").mkdir()
    (tmp_path / "models/orders.sql").write_text(
        "MODEL (materialized view, contract enforced, columns (quantity (type INTEGER), "
        "ordered_at (type TIMESTAMP)));\nSELECT CAST(1 AS INTEGER) AS quantity, "
        "CAST('2026-04-01' AS TIMESTAMP) AS ordered_at"
    )
    (tmp_path / "models/broken.sql").write_text(
        f"MODEL (materialized view{test_case.root_contract});\nSELECT quantity + ordered_at AS total, "
        'ordered_at FROM __ref("orders")'
    )
    (tmp_path / "models/downstream.sql").write_text(
        "MODEL (materialized view);\nSELECT total > ordered_at AS compared"
        + test_case.independent_sql
        + ' FROM __ref("broken")'
    )
    (tmp_path / "models/final_orders.sql").write_text(
        'MODEL (materialized view);\nSELECT compared AS final_value FROM __ref("downstream")'
    )
    main(["--project-dir", str(tmp_path), "compile", "--json"])
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    main(["--project-dir", str(tmp_path), "compile", "--json"])
    warm: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert warm["diagnostics"] == result["diagnostics"]
    assert warm["semantic_checks_partial"] == result["semantic_checks_partial"]
    assert sorted(item["code"] for item in result["diagnostics"]) == sorted(
        test_case.expected_codes
    ), result["diagnostics"]
    assert "downstream" in result["semantic_checks_partial"]
    notes: list[str] = []
    for item in result["diagnostics"]:
        notes.extend(item.get("notes", []))
    assert any("2 downstream output uses" in note for note in notes)


@pytest.mark.parametrize(
    "test_case",
    [SemanticTriageCase("repeated projections", expected_codes=("B217",))],
    ids=lambda case: case.description,
)
def test_given_repetitive_sql_when_mapping_diagnostic_then_preserves_authored_span(
    test_case: SemanticTriageCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text('name = "orders"\nadapter = "duckdb"\n')
    (tmp_path / "models").mkdir()
    (tmp_path / "models/orders.sql").write_text(
        "MODEL (materialized view);\nSELECT CAST(1 AS INTEGER) AS quantity"
    )
    projections: str = ",\n".join(f"quantity + {index} AS amount_{index}" for index in range(300))
    sql: str = (
        "MODEL (materialized view);\nSELECT\n"
        + projections
        + "\nFROM __ref(\"orders\")\nWHERE quantity > TIMESTAMP '2026-04-01'"
    )
    (tmp_path / "models/report.sql").write_text(sql)
    assert main(["--project-dir", str(tmp_path), "compile", "--no-cache", "--json"]) == 1
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in result["diagnostics"]) == test_case.expected_codes
    location: dict[str, Any] = result["diagnostics"][0]["location"]
    assert location["line"] == len(sql.splitlines())
    assert location["column"] == len("WHERE ") + 1
    assert location["end_column"] == len(sql.splitlines()[-1]) + 1


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
