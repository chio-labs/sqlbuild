"""Synthetic regressions for target semantics and error-local recovery."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

import sqlbuild._native as native
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
    assert physical == ()


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


@pytest.mark.parametrize(
    "test_case",
    [SemanticTriageCase("warm semantic cache", expected_codes=("B212",))],
    ids=lambda case: case.description,
)
def test_given_cached_validation_when_warm_or_schema_changed_then_reuses_only_matching_inputs(
    test_case: SemanticTriageCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "sources").mkdir()
    (tmp_path / "models").mkdir()
    source: Path = tmp_path / "sources/orders.yml"
    declaration: str = "sources:\n  - name: orders\n    table: orders\n    contract: enforced\n    columns:\n      - name: quantity\n        type: INTEGER\n"
    source.write_text(declaration)
    (tmp_path / "models/totals.sql").write_text(
        'MODEL (materialized view);\nSELECT quantity + 1 AS total FROM __source("orders")'
    )
    args: list[str] = ["--project-dir", str(tmp_path), "compile", "--json"]
    with monkeypatch.context() as patch:
        repeated_validation: Mock = Mock(
            side_effect=AssertionError("cold compile repeated fused validation")
        )
        patch.setattr(native, "validate_sql_with_schemas_json", repeated_validation)
        assert main(args) == 0
        repeated_validation.assert_not_called()
    capsys.readouterr()
    with monkeypatch.context() as patch:
        forbidden: Mock = Mock(
            side_effect=AssertionError("warm compile repeated native semantic work")
        )
        patch.setattr(native, "validate_sql_with_schemas_json", forbidden)
        patch.setattr(native, "analyze_project_queries_compact_json", forbidden)
        assert main(args) == 0
        forbidden.assert_not_called()
    capsys.readouterr()
    source.write_text(declaration.replace("INTEGER", "TIMESTAMP"))
    assert main(args) == 1
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in result["diagnostics"]) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [SemanticTriageCase("distinct spans with identical messages", expected_codes=("B212", "B212"))],
    ids=lambda case: case.description,
)
def test_given_repeated_root_messages_when_recovering_then_preserves_each_output_cause(
    test_case: SemanticTriageCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "orders"\nadapter = "duckdb"\n[rules]\nselect = []\n'
    )
    (tmp_path / "models").mkdir()
    files: dict[str, str] = {
        "orders": "MODEL (materialized view, contract enforced, columns (quantity (type INTEGER), ordered_at (type TIMESTAMP)));\nSELECT CAST(1 AS INTEGER) AS quantity, CAST('2026-04-01' AS TIMESTAMP) AS ordered_at",
        "broken": 'MODEL (materialized view, contract enforced, columns (total_a (type INTEGER), total_b (type INTEGER), ordered_at (type TIMESTAMP)));\nSELECT quantity + ordered_at AS total_a, quantity + ordered_at AS total_b, ordered_at FROM __ref("orders")',
        "downstream": 'MODEL (materialized view);\nSELECT total_a > ordered_at AS a, total_b > ordered_at AS b FROM __ref("broken")',
        "final_orders": 'MODEL (materialized view);\nSELECT a, b FROM __ref("downstream")',
    }
    for name, sql in files.items():
        (tmp_path / "models" / f"{name}.sql").write_text(sql)
    assert main(["--project-dir", str(tmp_path), "compile", "--json", "--no-cache"]) == 1
    result: dict[str, Any] = json.loads(capsys.readouterr().out)
    assert tuple(item["code"] for item in result["diagnostics"]) == test_case.expected_codes
    for diagnostic in result["diagnostics"]:
        assert (
            "2 downstream output uses were not type-checked because of this error"
            in diagnostic["notes"]
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
