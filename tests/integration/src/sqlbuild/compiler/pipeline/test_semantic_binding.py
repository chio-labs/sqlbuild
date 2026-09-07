"""Integration coverage for authoritative offline SQL column binding."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from tests.integration.src.sqlbuild.compiler.pipeline._test_types import (
    SemanticBindingClauseIntegrationTestCase,
    SemanticBindingIntegrationTestCase,
)
from tests.integration.src.sqlbuild.compiler.pipeline.helpers import write_semantic_binding_project

_AUTHORITATIVE_MODEL: str = """MODEL (
  materialized table
  contract enforced
  columns (
    id (type INTEGER)
    category (type VARCHAR)
  )
);
SELECT CAST(1 AS INTEGER) AS id, CAST('a' AS VARCHAR) AS category
"""


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingClauseIntegrationTestCase(
            description="where predicate",
            query_sql='SELECT id FROM __ref("upstream") WHERE missing_where = TRUE',
            missing_column="missing_where",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="join predicate",
            query_sql=(
                'SELECT l.id FROM __ref("upstream") l JOIN __ref("upstream") r '
                "ON l.id = r.missing_join"
            ),
            missing_column="missing_join",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="group by expression",
            query_sql=(
                'SELECT COUNT(*) AS count_rows FROM __ref("upstream") GROUP BY missing_group'
            ),
            missing_column="missing_group",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="having predicate",
            query_sql=(
                'SELECT category, COUNT(*) AS count_rows FROM __ref("upstream") '
                "GROUP BY category HAVING missing_having > 0"
            ),
            missing_column="missing_having",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="order by expression",
            query_sql='SELECT id FROM __ref("upstream") ORDER BY missing_order',
            missing_column="missing_order",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="window partition",
            query_sql=(
                "SELECT ROW_NUMBER() OVER (PARTITION BY missing_partition ORDER BY id) AS rn "
                'FROM __ref("upstream")'
            ),
            missing_column="missing_partition",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="window ordering",
            query_sql=(
                "SELECT ROW_NUMBER() OVER (PARTITION BY category ORDER BY missing_window_order) "
                'AS rn FROM __ref("upstream")'
            ),
            missing_column="missing_window_order",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="qualify predicate",
            query_sql=(
                "SELECT ROW_NUMBER() OVER (ORDER BY id) AS rn "
                'FROM __ref("upstream") QUALIFY missing_qualify = TRUE'
            ),
            missing_column="missing_qualify",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="join using",
            query_sql=(
                'SELECT l.id FROM __ref("upstream") l JOIN __ref("upstream") r '
                "USING (missing_using)"
            ),
            missing_column="missing_using",
        ),
        SemanticBindingClauseIntegrationTestCase(
            description="nested cte",
            query_sql=(
                'WITH scoped AS (SELECT id FROM __ref("upstream")) SELECT missing_cte FROM scoped'
            ),
            missing_column="missing_cte",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_complete_contract_when_clause_references_missing_column_then_compile_fails(
    test_case: SemanticBindingClauseIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=f"MODEL (materialized view);\n{test_case.query_sql}\n",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert (
        f"error[{test_case.expected_error_code}]: Unknown column '{test_case.missing_column}'"
        in output
    )
    assert "(context:" in output
    assert "model: downstream" in output
    assert "--> models/downstream.sql:2:" in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given two complete contracts when unqualified column is ambiguous then compile fails",
            expected_exit_code=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_two_complete_contracts_when_unqualified_column_is_ambiguous_then_compile_fails(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (materialized view);\n"
            'SELECT id FROM __ref("upstream") l CROSS JOIN __ref("other") r\n'
        ),
    )
    _ = (tmp_path / "models" / "other.sql").write_text(
        _AUTHORITATIVE_MODEL,
        encoding="utf-8",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B003]:" in output
    assert "id" in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given partial upstream when column absence is unproven then compile succeeds",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_upstream_when_column_absence_is_unproven_then_compile_succeeds(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql="MODEL (materialized table);\nSELECT id FROM raw_orders\n",
        downstream_sql=(
            'MODEL (materialized view);\nSELECT missing_column FROM __ref("upstream")\n'
        ),
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B" not in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given enforced source contract when column is missing then compile fails",
            expected_exit_code=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_enforced_source_contract_when_column_is_missing_then_compile_fails(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "semantic_binding"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    sources_dir: Path = tmp_path / "sources"
    models_dir: Path = tmp_path / "models"
    sources_dir.mkdir()
    models_dir.mkdir()
    _ = (sources_dir / "raw.yml").write_text(
        """sources:
  - name: raw_orders
    schema: raw
    table: orders
    contract: enforced
    columns:
      - name: id
        type: INTEGER
""",
        encoding="utf-8",
    )
    _ = (models_dir / "downstream.sql").write_text(
        'MODEL (materialized view);\nSELECT missing FROM __source("raw_orders")\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B002]: Unknown column 'missing' in table 'raw_orders'" in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given complete inferred intermediate when downstream column is missing then compile fails",
            expected_exit_code=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_complete_inferred_intermediate_when_downstream_column_is_missing_then_compile_fails(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (materialized view);\n"
            'SELECT id FROM __ref("intermediate") WHERE missing_derived = TRUE\n'
        ),
    )
    _ = (tmp_path / "models" / "intermediate.sql").write_text(
        'MODEL (materialized view);\nSELECT id FROM __ref("upstream")\n',
        encoding="utf-8",
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B002]: Unknown column 'missing_derived'" in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given model analysis disabled when column is missing then binding is skipped",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_analysis_disabled_when_column_is_missing_then_binding_is_skipped(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (materialized view, sql_analysis false);\n"
            'SELECT missing_vendor_column FROM __ref("upstream")\n'
        ),
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B" not in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given cli analysis disabled when sql is unsupported then compile succeeds",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_cli_analysis_disabled_when_sql_is_unsupported_then_compile_succeeds(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = (tmp_path / "sqlbuild_project.toml").write_text(
        'name = "semantic_binding"\nadapter = "duckdb"\n', encoding="utf-8"
    )
    models_dir: Path = tmp_path / "models"
    models_dir.mkdir()
    _ = (models_dir / "vendor.sql").write_text(
        "MODEL (materialized view);\nSELEC unsupported vendor sql\n",
        encoding="utf-8",
    )

    exit_code: int = main(
        [
            "--no-color",
            "--project-dir",
            str(tmp_path),
            "compile",
            "--no-sql-analysis",
        ]
    )

    _ = capsys.readouterr()
    assert exit_code == test_case.expected_exit_code


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given lineage uses requested when query filters then json keeps predicates separate",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_lineage_uses_requested_when_query_filters_then_json_keeps_predicates_separate(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (materialized view);\n"
            'SELECT id FROM __ref("upstream") u '
            "WHERE u.category = 'active' ORDER BY u.id\n"
        ),
    )

    exit_code: int = main(
        [
            "--project-dir",
            str(tmp_path),
            "lineage",
            "downstream",
            "--format",
            "json",
            "--include-uses",
        ]
    )

    payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert exit_code == test_case.expected_exit_code
    assert {(use["context"], use["source"]["column"]) for use in payload["semantic_uses"]} == {
        ("where", "category"),
        ("order_by", "id"),
    }
    assert all("semantic_uses" not in edge for edge in payload["edges"])

    default_exit_code: int = main(
        ["--project-dir", str(tmp_path), "lineage", "downstream", "--format", "json"]
    )
    default_payload: dict[str, object] = json.loads(capsys.readouterr().out)
    assert default_exit_code == 0
    assert "semantic_uses" not in default_payload


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given valid using and qualify alias when binding then compile succeeds",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_valid_using_and_qualify_alias_when_binding_then_compile_succeeds(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (materialized view);\n"
            "SELECT ROW_NUMBER() OVER (ORDER BY l.id) AS rn "
            'FROM __ref("upstream") l JOIN __ref("upstream") r USING (id) '
            "QUALIFY rn = 1\n"
        ),
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[B" not in output


@pytest.mark.parametrize(
    "test_case",
    [
        SemanticBindingIntegrationTestCase(
            description="given unresolved star when contract has additional column then absence is uncertain",
            expected_exit_code=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unresolved_star_when_contract_has_additional_column_then_compile_succeeds(
    test_case: SemanticBindingIntegrationTestCase,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    write_semantic_binding_project(
        project_dir=tmp_path,
        upstream_sql=_AUTHORITATIVE_MODEL,
        downstream_sql=(
            "MODEL (\n"
            "  materialized view\n"
            "  contract enforced\n"
            "  columns (\n"
            "    id (type INTEGER)\n"
            "    category (type VARCHAR)\n"
            "    runtime_column (type VARCHAR)\n"
            "  )\n"
            ");\n"
            'SELECT * FROM __ref("upstream")\n'
        ),
    )

    exit_code: int = main(["--no-color", "--project-dir", str(tmp_path), "compile", "--no-cache"])

    output: str = capsys.readouterr().out
    assert exit_code == test_case.expected_exit_code
    assert "error[K001]" not in output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
