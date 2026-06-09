from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.compiler.fingerprints.main.shared.helpers.sql import (
    build_create_table_sql,
    build_insert_sql,
)
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_standard_reuse_source_project,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    HookFunctionPlanOutputTestCase,
    StandardReuseFullRefreshBypassTestCase,
    StandardReuseSourcePlanOutputTestCase,
    StandardSourceFreshnessPlanOutputTestCase,
)

PLAN_OUTPUT_TEST_CASES: list[StandardSourceFreshnessPlanOutputTestCase] = [
    StandardSourceFreshnessPlanOutputTestCase(
        description="standard changes-only plan output carries source freshness result",
        changes_only=True,
        expected_has_source_freshness=True,
    ),
    StandardSourceFreshnessPlanOutputTestCase(
        description="normal standard plan output omits source freshness result",
        changes_only=False,
        expected_has_source_freshness=False,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    PLAN_OUTPUT_TEST_CASES,
    ids=[case.description for case in PLAN_OUTPUT_TEST_CASES],
)
def test_given_direct_plan_when_building_execution_plan_then_source_freshness_matches_changes_only(
    test_case: StandardSourceFreshnessPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        plan_output: PlanOutput = build_execution_plan(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
            ),
            adapter=adapter,
            connection=connection,
            changes_only=test_case.changes_only,
        )
    finally:
        adapter.close(connection)

    assert (plan_output.source_freshness is not None) == test_case.expected_has_source_freshness


@pytest.mark.parametrize(
    "test_case",
    [
        HookFunctionPlanOutputTestCase(
            description="execution plan carries discovered hook functions",
            expected_hook_names=("notify",),
        )
    ],
    ids=["execution plan carries discovered hook functions"],
)
def test_given_project_with_hook_functions_when_building_execution_plan_then_plan_carries_hooks(
    test_case: HookFunctionPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})

    def notify() -> None:
        return None

    try:
        plan_output: PlanOutput = build_execution_plan(
            project=CompiledProject(
                run_id="test_run",
                effective_target_name=None,
                effective_connection={},
                effective_vars={},
                hook_functions=(
                    DiscoveredHookFunction(
                        file_path=Path(__file__),
                        relative_path=Path("hooks/notify.py"),
                        name="notify",
                        function=notify,
                    ),
                ),
            ),
            adapter=adapter,
            connection=connection,
        )
    finally:
        adapter.close(connection)

    assert tuple(hook.name for hook in plan_output.hook_functions) == test_case.expected_hook_names


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseSourcePlanOutputTestCase(
            description="execution plan carries standard reuse source metadata",
            expected_source_target_name="prod",
            expected_model_names=("customers", "orders"),
            expected_reuse_candidate_names=(),
            expected_decisions={
                "customers": "source_fingerprint_missing",
                "orders": "source_version_mismatch",
            },
        )
    ],
    ids=["execution plan carries standard reuse source metadata"],
)
def test_given_reuse_from_target_when_building_execution_plan_then_plan_carries_source_metadata(
    test_case: StandardReuseSourcePlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, "CREATE SCHEMA dev_schema")
        adapter.execute(connection, "CREATE SCHEMA prod_schema")
        adapter.execute(
            connection,
            build_create_table_sql(
                database=None,
                schema="prod_schema",
                render_qualified_name=adapter.render_qualified_name,
                render_framework_type=adapter.render_framework_type,
            ),
        )
        adapter.execute(
            connection,
            build_insert_sql(
                database=None,
                schema="prod_schema",
                model_name="orders",
                target_database=None,
                target_schema="prod_schema",
                target_name="orders",
                run_id="run_1",
                query_hash="query_hash",
                version_hash="orders_version_hash",
                schema_fingerprint="schema_hash",
                query_sql="SELECT 1",
                metadata_json="{}",
                ts="2026-01-01T00:00:00+00:00",
                render_qualified_name=adapter.render_qualified_name,
            ),
        )
        adapter.execute(connection, "CREATE TABLE prod_schema.orders AS SELECT 1 AS id")

        plan_output: PlanOutput = build_execution_plan(
            project=build_standard_reuse_source_project(),
            adapter=adapter,
            connection=connection,
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                    "prod": TargetConfig(schema="prod_schema"),
                },
            ),
            local_config=LocalConfig(),
        )
    finally:
        adapter.close(connection)

    metadata: dict[str, object] = plan_output.metadata
    reuse_metadata: object = metadata.get("standard_reuse_source")
    assert isinstance(reuse_metadata, dict)
    typed_reuse_metadata: dict[str, object] = cast(dict[str, object], reuse_metadata)
    assert typed_reuse_metadata["target_name"] == test_case.expected_source_target_name
    models_metadata: object = typed_reuse_metadata["models"]
    assert isinstance(models_metadata, dict)
    assert tuple(sorted(models_metadata)) == test_case.expected_model_names
    decisions_metadata: object = metadata.get("standard_reuse_decisions")
    assert isinstance(decisions_metadata, dict)
    typed_decisions_metadata: dict[str, object] = cast(dict[str, object], decisions_metadata)
    decision_models_metadata: object = typed_decisions_metadata["models"]
    assert isinstance(decision_models_metadata, dict)
    assert {
        model_name: cast(dict[str, object], model_metadata).get("decision")
        for model_name, model_metadata in decision_models_metadata.items()
        if isinstance(model_metadata, dict)
    } == test_case.expected_decisions
    assert (
        tuple(
            sorted(
                model_name
                for model_name, model_metadata in decision_models_metadata.items()
                if isinstance(model_metadata, dict)
                and cast(dict[str, object], model_metadata).get("decision") == "reuse_candidate"
            )
        )
        == test_case.expected_reuse_candidate_names
    )


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFullRefreshBypassTestCase(
            description="full refresh bypasses standard reuse source state",
            expected_reuse_source_metadata_present=False,
            expected_reuse_decision_metadata_present=False,
        )
    ],
    ids=["full refresh bypasses standard reuse source state"],
)
def test_given_full_refresh_with_reuse_from_when_planning_then_reuse_state_is_skipped(
    test_case: StandardReuseFullRefreshBypassTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, "CREATE SCHEMA dev_schema")
        plan_output: PlanOutput = build_execution_plan(
            project=build_standard_reuse_source_project(),
            adapter=adapter,
            connection=connection,
            full_refresh=True,
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(schema="dev_schema", reuse_from="prod"),
                    "prod": TargetConfig(schema="prod_schema"),
                },
            ),
            local_config=LocalConfig(),
        )
    finally:
        adapter.close(connection)

    assert (
        "standard_reuse_source" in plan_output.metadata
    ) is test_case.expected_reuse_source_metadata_present
    assert (
        "standard_reuse_decisions" in plan_output.metadata
    ) is test_case.expected_reuse_decision_metadata_present
