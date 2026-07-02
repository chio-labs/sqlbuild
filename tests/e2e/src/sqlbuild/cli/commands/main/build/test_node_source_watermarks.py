from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    NodeSourceWatermarkBuildE2ETestCase,
    NodeSourceWatermarkWarningBuildE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    build_frontier_inputs_for_node_source_watermark_case,
    latest_node_source_watermark_payloads,
    node_source_watermark_kinds_by_node,
    node_source_watermark_unknown_reasons_by_node,
    node_source_watermark_versions_by_node,
    prepare_node_source_watermark_project,
    replace_raw_orders_versions,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import execute_duckdb, run_sqb


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkBuildE2ETestCase(
            description="table reaches source frontier through view",
            project_name="node_watermark_view_source",
            expected_source_versions_by_node={"a": ("1",)},
            expected_source_kinds_by_node={"a": ("direct",)},
            expected_absent_nodes=("v",),
        )
    ],
    ids=["table reaches source frontier through view"],
)
def test_given_table_reads_view_over_source_when_build_runs_then_records_direct_watermark(
    test_case: NodeSourceWatermarkBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_node_source_watermark_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        models={
            "models/v.sql": dedent(
                """
                MODEL (materialized view);

                SELECT id FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/a.sql": dedent(
                """
                MODEL (materialized table);

                SELECT id FROM __ref("v")
                """
            ).strip()
            + "\n",
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    replace_raw_orders_versions(db_path=db_path, versions=(1,))

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payloads: dict[str, dict[str, Any]] = latest_node_source_watermark_payloads(db_path=db_path)
    assert (
        node_source_watermark_versions_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_versions_by_node
    )
    assert (
        node_source_watermark_kinds_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_kinds_by_node
    )
    absent_node: str
    for absent_node in test_case.expected_absent_nodes:
        assert absent_node not in payloads


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkBuildE2ETestCase(
            description="table reaches materialized frontier through view",
            project_name="node_watermark_view_table",
            expected_source_versions_by_node={"a": ("1",)},
            expected_source_kinds_by_node={"a": ("inherited",)},
            expected_absent_nodes=("v",),
        )
    ],
    ids=["table reaches materialized frontier through view"],
)
def test_given_table_reads_view_over_table_when_source_advances_then_inherits_table_watermark(
    test_case: NodeSourceWatermarkBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_node_source_watermark_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        models={
            "models/b.sql": dedent(
                """
                MODEL (materialized table);

                SELECT id FROM __source("raw_orders")
                """
            ).strip()
            + "\n",
            "models/v.sql": dedent(
                """
                MODEL (materialized view);

                SELECT id FROM __ref("b")
                """
            ).strip()
            + "\n",
            "models/a.sql": dedent(
                """
                MODEL (materialized table);

                SELECT id FROM __ref("v")
                """
            ).strip()
            + "\n",
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    replace_raw_orders_versions(db_path=db_path, versions=(1,))
    initial_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"),
        project_dir=project_dir,
    )
    replace_raw_orders_versions(db_path=db_path, versions=(2,))

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--force", "--select", "a"),
        project_dir=project_dir,
    )

    assert initial_result.returncode == 0, initial_result.stdout + initial_result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    payloads: dict[str, dict[str, Any]] = latest_node_source_watermark_payloads(db_path=db_path)
    assert (
        node_source_watermark_versions_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_versions_by_node
    )
    assert (
        node_source_watermark_kinds_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_kinds_by_node
    )
    absent_node: str
    for absent_node in test_case.expected_absent_nodes:
        assert absent_node not in payloads


MERGED_FRONTIER_TEST_CASES: list[NodeSourceWatermarkBuildE2ETestCase] = [
    NodeSourceWatermarkBuildE2ETestCase(
        description="both upstream frontier tables current",
        project_name="node_watermark_merged_current",
        expected_source_versions_by_node={"a": ("2",)},
        expected_source_kinds_by_node={"a": ("inherited",)},
    ),
    NodeSourceWatermarkBuildE2ETestCase(
        description="both upstream frontier tables stale",
        project_name="node_watermark_merged_stale",
        expected_source_versions_by_node={"a": ("1",)},
        expected_source_kinds_by_node={"a": ("inherited",)},
    ),
    NodeSourceWatermarkBuildE2ETestCase(
        description="one upstream frontier table stale and one current",
        project_name="node_watermark_merged_mixed",
        expected_source_versions_by_node={"a": ("1",)},
        expected_source_kinds_by_node={"a": ("inherited",)},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    MERGED_FRONTIER_TEST_CASES,
    ids=[case.description for case in MERGED_FRONTIER_TEST_CASES],
)
def test_given_table_reads_two_frontier_tables_when_build_runs_then_keeps_oldest_watermark(
    test_case: NodeSourceWatermarkBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_node_source_watermark_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        models={
            "models/b.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/c.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/a.sql": (
                "MODEL (materialized table);\n\n"
                'SELECT b.id FROM __ref("b") b JOIN __ref("c") c USING (id)\n'
            ),
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    build_frontier_inputs_for_node_source_watermark_case(
        project_dir=project_dir,
        db_path=db_path,
        test_case=test_case,
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--force", "--select", "a"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payloads: dict[str, dict[str, Any]] = latest_node_source_watermark_payloads(db_path=db_path)
    assert (
        node_source_watermark_versions_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_versions_by_node
    )
    assert (
        node_source_watermark_kinds_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_kinds_by_node
    )


@pytest.mark.parametrize(
    "test_case",
    [
        NodeSourceWatermarkBuildE2ETestCase(
            description="missing upstream frontier watermark records unknown",
            project_name="node_watermark_missing_upstream",
            expected_source_versions_by_node={"a": ()},
            expected_source_kinds_by_node={"a": ()},
            expected_unknown_reasons_by_node={"a": ("missing_upstream_watermark",)},
        )
    ],
    ids=["missing upstream frontier watermark records unknown"],
)
def test_given_upstream_table_exists_without_watermark_when_downstream_runs_then_records_unknown(
    test_case: NodeSourceWatermarkBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_node_source_watermark_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        models={
            "models/b.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/a.sql": 'MODEL (materialized table);\n\nSELECT id FROM __ref("b")\n',
        },
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    replace_raw_orders_versions(db_path=db_path, versions=(2,))
    execute_duckdb(db_path=db_path, sql="CREATE TABLE b AS SELECT 1 AS id")

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--force", "--select", "a"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payloads: dict[str, dict[str, Any]] = latest_node_source_watermark_payloads(db_path=db_path)
    assert (
        node_source_watermark_versions_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_versions_by_node
    )
    assert (
        node_source_watermark_kinds_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_source_kinds_by_node
    )
    assert (
        node_source_watermark_unknown_reasons_by_node(payloads=payloads, test_case=test_case)
        == test_case.expected_unknown_reasons_by_node
    )


WARNING_TEST_CASES: list[NodeSourceWatermarkWarningBuildE2ETestCase] = [
    NodeSourceWatermarkWarningBuildE2ETestCase(
        description="materialized frontier behind source emits grouped warning",
        project_name="node_watermark_warning_stale_frontier",
        models={
            "models/b.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/a.sql": 'MODEL (materialized table);\n\nSELECT id FROM __ref("b")\n',
        },
        setup_build_command=("--no-color", "build", "--select", "b"),
        plan_command=("--no-color", "plan", "--select", "a"),
        expected_stdout_fragments=(
            "Warnings (1)",
            "Stale inputs detected",
            "Affected selected models:",
            "a",
            "Stale frontier tables:",
            "b",
            "Changed sources:",
            "raw_orders",
            "rebuild the upstream closure for the selected model(s)",
        ),
    ),
    NodeSourceWatermarkWarningBuildE2ETestCase(
        description="direct source frontier does not emit stale-input warning",
        project_name="node_watermark_warning_direct_source",
        models={
            "models/a.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
        },
        setup_build_command=("--no-color", "build", "--select", "a"),
        plan_command=("--no-color", "plan", "--select", "a"),
        expected_stdout_fragments=("Source freshness", "source-stale models: a"),
        unexpected_stdout_fragments=("Warnings (1)", "Stale inputs detected"),
    ),
    NodeSourceWatermarkWarningBuildE2ETestCase(
        description="shared stale frontier table appears once for multiple selected roots",
        project_name="node_watermark_warning_shared_stale_frontier",
        models={
            "models/b.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/a1.sql": 'MODEL (materialized table);\n\nSELECT id FROM __ref("b")\n',
            "models/a2.sql": 'MODEL (materialized table);\n\nSELECT id FROM __ref("b")\n',
        },
        setup_build_command=("--no-color", "build", "--select", "b"),
        plan_command=("--no-color", "plan", "--select", "a1", "--select", "a2"),
        expected_stdout_fragments=(
            "Warnings (1)",
            "Stale inputs detected",
            "Affected selected models:",
            "a1",
            "a2",
            "Stale frontier tables:",
            "b",
            "Changed sources:",
            "raw_orders",
        ),
        expected_stdout_occurrences={
            "\n        b\n": 1,
            "\n        raw_orders\n": 1,
        },
    ),
    NodeSourceWatermarkWarningBuildE2ETestCase(
        description="selected root behind refreshed frontier table emits grouped warning",
        project_name="node_watermark_warning_root_behind_frontier",
        models={
            "models/b.sql": (
                'MODEL (materialized table);\n\nSELECT id FROM __source("raw_orders")\n'
            ),
            "models/a.sql": 'MODEL (materialized table);\n\nSELECT id FROM __ref("b")\n',
        },
        setup_build_command=("--no-color", "build"),
        setup_after_source_advance_commands=(("--no-color", "build", "--select", "b"),),
        plan_command=("--no-color", "plan", "--select", "a"),
        expected_stdout_fragments=(
            "Warnings (1)",
            "Stale inputs detected",
            "Affected selected models:",
            "a",
            "Stale frontier tables:",
            "b",
            "Changed sources:",
            "raw_orders",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    WARNING_TEST_CASES,
    ids=[case.description for case in WARNING_TEST_CASES],
)
def test_given_source_advances_when_planning_selection_then_reports_expected_stale_inputs(
    test_case: NodeSourceWatermarkWarningBuildE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_node_source_watermark_project(
        tmp_path=tmp_path,
        project_name=test_case.project_name,
        models=test_case.models,
    )
    db_path: Path = project_dir / "warehouse.duckdb"
    replace_raw_orders_versions(db_path=db_path, versions=(1,))
    setup_result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.setup_build_command,
        project_dir=project_dir,
    )
    replace_raw_orders_versions(db_path=db_path, versions=(2,))
    setup_after_source_advance_command: tuple[str, ...]
    for setup_after_source_advance_command in test_case.setup_after_source_advance_commands:
        followup_result: subprocess.CompletedProcess[str] = run_sqb(
            command=setup_after_source_advance_command,
            project_dir=project_dir,
        )
        assert followup_result.returncode == 0, followup_result.stdout + followup_result.stderr

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.plan_command,
        project_dir=project_dir,
    )

    assert setup_result.returncode == 0, setup_result.stdout + setup_result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    expected_fragment: str
    for expected_fragment in test_case.expected_stdout_fragments:
        assert expected_fragment in result.stdout
    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_stdout_fragments:
        assert unexpected_fragment not in result.stdout
    fragment: str
    expected_count: int
    for fragment, expected_count in test_case.expected_stdout_occurrences.items():
        assert result.stdout.count(fragment) == expected_count
