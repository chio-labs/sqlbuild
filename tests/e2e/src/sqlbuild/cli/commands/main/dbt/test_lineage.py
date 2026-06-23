from __future__ import annotations

import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import (
    DbtColumnLineageE2ETestCase,
    DbtLineageE2ETestCase,
    DbtLineageErrorE2ETestCase,
    DbtLineageTextE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import (
    apply_dbt_lineage_error_setup,
    assert_dbt_column_lineage_json_payload,
    assert_dbt_lineage_json_payload,
    drop_dbt_phase11_orders_source_table,
    load_json_stdout,
    prepare_dbt_phase11_project,
    remove_dbt_phase11_sqlbuild_models,
    skip_unless_dbt_is_runnable,
    write_dbt_phase11_invalid_sqlbuild_model,
    write_dbt_phase11_missing_ref_model,
    write_dbt_phase11_star_lineage_models,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import run_sqb

pytestmark: pytest.MarkDecorator = pytest.mark.dbt

LINEAGE_TEST_CASES: tuple[DbtLineageE2ETestCase, ...] = (
    DbtLineageE2ETestCase(
        description="SQLBuild model traces upstream through dbt models to dbt source",
        command=("dbt", "lineage", "downstream_orders", "--format", "json"),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "dbt:model:model.analytics.stg_orders",
            "dbt:source:source.analytics.raw.orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
            ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),
        ),
        expected_focus=("sqb:model:downstream_orders",),
        expected_direction="upstream",
        expected_node_metadata=(
            ("dbt:model:model.analytics.fact_orders", "label", "fact_orders"),
            (
                "dbt:model:model.analytics.fact_orders",
                "qualified_name",
                '"dbt_phase11"."main"."fact_orders"',
            ),
            ("dbt:model:model.analytics.fact_orders", "relative_path", "models/fact_orders.sql"),
            ("sqb:model:downstream_orders", "relative_path", "models/downstream_orders.sql"),
        ),
    ),
    DbtLineageE2ETestCase(
        description="dbt model traces downstream into SQLBuild model",
        command=(
            "dbt",
            "lineage",
            "model.analytics.stg_orders",
            "--format",
            "json",
            "--direction",
            "downstream",
        ),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "dbt:model:model.analytics.stg_orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
            ("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),
        ),
        expected_focus=("dbt:model:model.analytics.stg_orders",),
        expected_direction="downstream",
    ),
    DbtLineageE2ETestCase(
        description="dbt model traces both directions across dbt and SQLBuild models",
        command=(
            "dbt",
            "lineage",
            "model.analytics.fact_orders",
            "--format",
            "json",
            "--direction",
            "both",
        ),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "dbt:model:model.analytics.stg_orders",
            "dbt:source:source.analytics.raw.orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
            ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),
        ),
        expected_focus=("dbt:model:model.analytics.fact_orders",),
        expected_direction="both",
    ),
    DbtLineageE2ETestCase(
        description="depth limits upstream traversal",
        command=("dbt", "lineage", "downstream_orders", "--format", "json", "--depth", "1"),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),),
        expected_focus=("sqb:model:downstream_orders",),
        expected_direction="upstream",
    ),
    DbtLineageE2ETestCase(
        description="dbt source unique id traces downstream into SQLBuild model",
        command=(
            "dbt",
            "lineage",
            "source.analytics.raw.orders",
            "--format",
            "json",
            "--direction",
            "downstream",
        ),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "dbt:model:model.analytics.stg_orders",
            "dbt:source:source.analytics.raw.orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
            ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),
        ),
        expected_focus=("dbt:source:source.analytics.raw.orders",),
        expected_direction="downstream",
    ),
    DbtLineageE2ETestCase(
        description="no sql validation flag still outputs lineage",
        command=(
            "dbt",
            "lineage",
            "downstream_orders",
            "--format",
            "json",
            "--no-sql-validation",
        ),
        expected_node_ids=(
            "dbt:model:model.analytics.fact_orders",
            "dbt:model:model.analytics.stg_orders",
            "dbt:source:source.analytics.raw.orders",
            "sqb:model:downstream_orders",
        ),
        expected_edges=(
            ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
            ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ("dbt:model:model.analytics.fact_orders", "sqb:model:downstream_orders"),
        ),
        expected_focus=("sqb:model:downstream_orders",),
        expected_direction="upstream",
    ),
)

LINEAGE_TEXT_TEST_CASES: tuple[DbtLineageTextE2ETestCase, ...] = (
    DbtLineageTextE2ETestCase(
        description="formats edge list",
        command=("--no-color", "dbt", "lineage", "downstream_orders", "--format", "list"),
        expected_stdout_fragments=(
            "stg_orders [dbt]",
            "fact_orders [dbt]",
            "raw.orders [dbt]",
            "downstream_orders [sqb]",
            "->",
        ),
        expected_stderr_fragments=("Compiling dbt project...", "Loaded dbt manifest."),
    ),
    DbtLineageTextE2ETestCase(
        description="formats tree output",
        command=("--no-color", "dbt", "lineage", "downstream_orders", "--format", "tree"),
        expected_stdout_fragments=(
            "Lineage  downstream_orders [sqb]  upstream",
            "└── fact_orders [dbt]",
            "└── stg_orders [dbt]",
            "└── raw.orders [dbt]",
        ),
        expected_stderr_fragments=("Compiling dbt project...", "Loaded dbt manifest."),
    ),
)

LINEAGE_ERROR_TEST_CASES: tuple[DbtLineageErrorE2ETestCase, ...] = (
    DbtLineageErrorE2ETestCase(
        description="renders invalid format error",
        command=("dbt", "lineage", "downstream_orders", "--format", "yaml"),
        expected_stderr_fragments=("--format must be tree, json, or list", "C334"),
    ),
    DbtLineageErrorE2ETestCase(
        description="renders missing target error",
        command=("dbt", "lineage", "--format", "json"),
        expected_stderr_fragments=(
            "dbt lineage requires a lineage target resource",
            "sqb dbt lineage dbt_orders",
            "C333",
        ),
    ),
    DbtLineageErrorE2ETestCase(
        description="renders dbt compile failure",
        command=("dbt", "lineage", "downstream_orders", "--format", "json"),
        expected_stderr_fragments=("dbt compile failed", "does_not_exist"),
        setup=write_dbt_phase11_missing_ref_model,
    ),
    DbtLineageErrorE2ETestCase(
        description="forwards dbt args into compile",
        command=("dbt", "lineage", "downstream_orders", "--format", "json", "--target", "missing"),
        expected_stderr_fragments=("dbt compile failed", "missing"),
    ),
    DbtLineageErrorE2ETestCase(
        description="fails invalid SQLBuild SQL without validation bypass",
        command=("dbt", "lineage", "invalid_sql", "--format", "json"),
        expected_stderr_fragments=("error[P001]", "--no-sql-validation"),
        setup=write_dbt_phase11_invalid_sqlbuild_model,
    ),
    DbtLineageErrorE2ETestCase(
        description="renders malformed column target error",
        command=("dbt", "lineage", "downstream_orders:", "--format", "json"),
        expected_stderr_fragments=("unknown dbt lineage target 'downstream_orders:'", "C331"),
    ),
)

COLUMN_LINEAGE_TEST_CASES: tuple[DbtColumnLineageE2ETestCase, ...] = (
    DbtColumnLineageE2ETestCase(
        description="traces SQLBuild column upstream through compiled dbt SQL",
        command=("dbt", "lineage", "downstream_orders:downstream_amount", "--format", "json"),
        expected_target=("model", "downstream_orders", "downstream_amount"),
        expected_edges=(
            ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
        ),
        expected_direction="upstream",
    ),
    DbtColumnLineageE2ETestCase(
        description="traces dbt source column downstream through compiled dbt SQL",
        command=(
            "dbt",
            "lineage",
            "source.analytics.raw.orders:amount",
            "--format",
            "json",
            "--direction",
            "downstream",
        ),
        expected_target=("source", "source.analytics.raw.orders", "amount"),
        expected_edges=(
            ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
            ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
        ),
        expected_direction="downstream",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_TEST_CASES,
    ids=[case.description for case in LINEAGE_TEST_CASES],
)
def test_given_dbt_interop_project_when_running_lineage_json_then_outputs_mixed_graph(
    tmp_path: Path,
    test_case: DbtLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    assert_dbt_lineage_json_payload(
        payload=payload,
        expected_node_ids=test_case.expected_node_ids,
        expected_edges=test_case.expected_edges,
        expected_focus=test_case.expected_focus,
        expected_direction=test_case.expected_direction,
        expected_node_metadata=test_case.expected_node_metadata,
    )


@pytest.mark.parametrize(
    "test_case",
    COLUMN_LINEAGE_TEST_CASES,
    ids=[case.description for case in COLUMN_LINEAGE_TEST_CASES],
)
def test_given_dbt_interop_project_when_running_column_lineage_json_then_outputs_column_trace(
    tmp_path: Path,
    test_case: DbtColumnLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    assert_dbt_column_lineage_json_payload(
        payload=payload,
        expected_target=test_case.expected_target,
        expected_edges=test_case.expected_edges,
        expected_direction=test_case.expected_direction,
        expected_warnings=test_case.expected_warnings,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageE2ETestCase(
            description="expands star lineage from adapter-described dbt source schema",
            command=("dbt", "lineage", "downstream_orders:downstream_amount", "--format", "json"),
            expected_target=("model", "downstream_orders", "downstream_amount"),
            expected_edges=(
                ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
                ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
                ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ),
            expected_direction="upstream",
        )
    ],
    ids=["expands star lineage from adapter-described dbt source schema"],
)
def test_given_star_dbt_models_when_running_column_lineage_json_then_uses_source_schema(
    tmp_path: Path,
    test_case: DbtColumnLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    write_dbt_phase11_star_lineage_models(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    assert_dbt_column_lineage_json_payload(
        payload=payload,
        expected_target=test_case.expected_target,
        expected_edges=test_case.expected_edges,
        expected_direction=test_case.expected_direction,
        expected_warnings=test_case.expected_warnings,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtColumnLineageE2ETestCase(
            description="warns and returns best-effort trace when dbt source schema is missing",
            command=("dbt", "lineage", "downstream_orders:downstream_amount", "--format", "json"),
            expected_target=("model", "downstream_orders", "downstream_amount"),
            expected_edges=(
                ("model.analytics.fact_orders:amount", "downstream_orders:downstream_amount"),
                ("model.analytics.stg_orders:amount", "model.analytics.fact_orders:amount"),
                ("source.analytics.raw.orders:amount", "model.analytics.stg_orders:amount"),
            ),
            expected_direction="upstream",
            expected_warnings=(
                "Could not inspect source source.analytics.raw.orders; "
                "SELECT * lineage from this source may be incomplete: ",
            ),
        )
    ],
    ids=["warns and returns best-effort trace when dbt source schema is missing"],
)
def test_given_missing_dbt_source_table_when_running_column_lineage_json_then_warns_and_traces(
    tmp_path: Path,
    test_case: DbtColumnLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    drop_dbt_phase11_orders_source_table(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    metadata_payload: object = payload["metadata"]
    assert isinstance(metadata_payload, dict)
    metadata: Mapping[str, object] = cast(Mapping[str, object], metadata_payload)
    warnings_payload: object = metadata["warnings"]
    assert isinstance(warnings_payload, list)
    assert_dbt_column_lineage_json_payload(
        payload=payload,
        expected_target=test_case.expected_target,
        expected_edges=test_case.expected_edges,
        expected_direction=test_case.expected_direction,
        expected_warnings=tuple(str(warning) for warning in warnings_payload),
    )
    assert len(warnings_payload) == 1
    assert test_case.expected_warnings[0] in str(warnings_payload[0])


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_TEXT_TEST_CASES,
    ids=[case.description for case in LINEAGE_TEXT_TEST_CASES],
)
def test_given_dbt_interop_project_when_running_lineage_text_then_outputs_human_graph(
    tmp_path: Path,
    test_case: DbtLineageTextE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    for expected_fragment in test_case.expected_stderr_fragments:
        assert expected_fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_ERROR_TEST_CASES,
    ids=[case.description for case in LINEAGE_ERROR_TEST_CASES],
)
def test_given_invalid_dbt_lineage_request_when_running_cli_then_renders_error(
    tmp_path: Path,
    test_case: DbtLineageErrorE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    apply_dbt_lineage_error_setup(project_dir=project_dir, test_case=test_case)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode != 0, result.stdout
    for expected_fragment in test_case.expected_stderr_fragments:
        assert expected_fragment in result.stderr


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageE2ETestCase(
            description="no sql validation bypasses invalid SQLBuild SQL",
            command=(
                "dbt",
                "lineage",
                "invalid_sql",
                "--format",
                "json",
                "--no-sql-validation",
            ),
            expected_node_ids=("sqb:model:invalid_sql",),
            expected_edges=(),
            expected_focus=("sqb:model:invalid_sql",),
            expected_direction="upstream",
        )
    ],
    ids=["no sql validation bypasses invalid SQLBuild SQL"],
)
def test_given_invalid_sqlbuild_sql_when_running_lineage_with_no_sql_validation_then_outputs_graph(
    tmp_path: Path,
    test_case: DbtLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    write_dbt_phase11_invalid_sqlbuild_model(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    assert_dbt_lineage_json_payload(
        payload=payload,
        expected_node_ids=test_case.expected_node_ids,
        expected_edges=test_case.expected_edges,
        expected_focus=test_case.expected_focus,
        expected_direction=test_case.expected_direction,
        expected_node_metadata=test_case.expected_node_metadata,
    )


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageE2ETestCase(
            description="dbt-only project traces model upstream to dbt source",
            command=("dbt", "lineage", "fact_orders", "--format", "json"),
            expected_node_ids=(
                "dbt:model:model.analytics.fact_orders",
                "dbt:model:model.analytics.stg_orders",
                "dbt:source:source.analytics.raw.orders",
            ),
            expected_edges=(
                ("dbt:model:model.analytics.stg_orders", "dbt:model:model.analytics.fact_orders"),
                ("dbt:source:source.analytics.raw.orders", "dbt:model:model.analytics.stg_orders"),
            ),
            expected_focus=("dbt:model:model.analytics.fact_orders",),
            expected_direction="upstream",
        )
    ],
    ids=["dbt-only project traces model upstream to dbt source"],
)
def test_given_dbt_only_project_when_running_lineage_json_then_outputs_dbt_graph(
    tmp_path: Path,
    test_case: DbtLineageE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    project_dir: Path = prepare_dbt_phase11_project(tmp_path=tmp_path)
    remove_dbt_phase11_sqlbuild_models(project_dir=project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    payload: dict[str, object] = load_json_stdout(result.stdout)
    assert_dbt_lineage_json_payload(
        payload=payload,
        expected_node_ids=test_case.expected_node_ids,
        expected_edges=test_case.expected_edges,
        expected_focus=test_case.expected_focus,
        expected_direction=test_case.expected_direction,
        expected_node_metadata=test_case.expected_node_metadata,
    )
