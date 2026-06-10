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
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.version_identity import (
    build_standard_model_version_identities,
)
from sqlbuild.compiler.planner.main.execution import build_execution_plan
from sqlbuild.compiler.planner.models import (
    ModelPlanEntry,
    PlanOutput,
    StandardModelVersionIdentities,
)
from sqlbuild.compiler.planner.types import PlanAction
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_standard_reuse_from_target_project,
    build_standard_reuse_from_target_scope,
)
from tests.unit.src.sqlbuild.compiler.planner.main._test_types import (
    HookFunctionPlanOutputTestCase,
    StandardReuseFromSourceDeferralConflictTestCase,
    StandardReuseFromTargetPlanOutputTestCase,
    StandardReuseFullRefreshBypassTestCase,
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

SOURCE_DEFERRAL_CONFLICT_TEST_CASES: list[StandardReuseFromSourceDeferralConflictTestCase] = [
    StandardReuseFromSourceDeferralConflictTestCase(
        description="target source deferral conflicts with standard reuse",
        defer_sources_to=None,
        target_defer_sources_to="prod_sources",
        expected_error_fragment="source deferral is active",
    ),
    StandardReuseFromSourceDeferralConflictTestCase(
        description="cli source deferral conflicts with standard reuse",
        defer_sources_to="prod_sources",
        target_defer_sources_to=None,
        expected_error_fragment="source deferral is active",
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
        StandardReuseFromTargetPlanOutputTestCase(
            description="execution plan carries standard reuse_from metadata",
            expected_reuse_from_target_name="prod",
            expected_model_names=("customers", "line_items", "orders"),
            expected_reuse_eligible_names=("line_items", "orders"),
            expected_decisions={
                "customers": "reuse_origin_fingerprint_missing",
                "line_items": "reuse_eligible",
                "orders": "reuse_eligible",
            },
            expected_actions={
                "customers": PlanAction.CREATE_TABLE.value,
                "line_items": PlanAction.INCREMENTAL_APPEND.value,
                "orders": PlanAction.REUSE_RELATION.value,
            },
        )
    ],
    ids=["execution plan carries standard reuse_from metadata"],
)
def test_given_reuse_from_target_when_building_execution_plan_then_plan_carries_reuse_metadata(
    test_case: StandardReuseFromTargetPlanOutputTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    project: CompiledProject = build_standard_reuse_from_target_project()
    version_identities: StandardModelVersionIdentities = build_standard_model_version_identities(
        functions=project.functions,
        scope=build_standard_reuse_from_target_scope(),
    )
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
                version_hash=version_identities.model_version_hashes["orders"],
                schema_fingerprint="schema_hash",
                query_sql="SELECT 1",
                metadata_json="{}",
                ts="2026-01-01T00:00:00+00:00",
                render_qualified_name=adapter.render_qualified_name,
            ),
        )
        adapter.execute(
            connection,
            build_insert_sql(
                database=None,
                schema="prod_schema",
                model_name="line_items",
                target_database=None,
                target_schema="prod_schema",
                target_name="line_items",
                run_id="run_1",
                query_hash="query_hash",
                version_hash=version_identities.model_version_hashes["line_items"],
                schema_fingerprint="schema_hash",
                query_sql="SELECT 1",
                metadata_json="{}",
                ts="2026-01-01T00:00:00+00:00",
                render_qualified_name=adapter.render_qualified_name,
            ),
        )
        adapter.execute(connection, "CREATE TABLE prod_schema.orders AS SELECT 1 AS id")
        adapter.execute(connection, "CREATE TABLE prod_schema.line_items AS SELECT 1 AS id")

        plan_output: PlanOutput = build_execution_plan(
            project=project,
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
    reuse_metadata: object = metadata.get("standard_reuse_from_target")
    assert isinstance(reuse_metadata, dict)
    typed_reuse_metadata: dict[str, object] = cast(dict[str, object], reuse_metadata)
    assert (
        typed_reuse_metadata["reuse_from_target_name"] == test_case.expected_reuse_from_target_name
    )
    models_metadata: object = typed_reuse_metadata["model_origins"]
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
                and cast(dict[str, object], model_metadata).get("decision") == "reuse_eligible"
            )
        )
        == test_case.expected_reuse_eligible_names
    )
    assert {entry.name: entry.action.value for entry in plan_output.model_entries} == (
        test_case.expected_actions
    )
    reuse_entry: ModelPlanEntry | None = next(
        (entry for entry in plan_output.model_entries if entry.name == "orders"), None
    )
    assert reuse_entry is not None
    assert reuse_entry.reuse_origin is not None
    assert reuse_entry.reuse_origin.qualified_name == "prod_schema.orders"
    seed_entry: ModelPlanEntry | None = next(
        (entry for entry in plan_output.model_entries if entry.name == "line_items"), None
    )
    assert seed_entry is not None
    assert seed_entry.reuse_origin is not None
    assert seed_entry.reuse_origin.qualified_name == "prod_schema.line_items"


@pytest.mark.parametrize(
    "test_case",
    SOURCE_DEFERRAL_CONFLICT_TEST_CASES,
    ids=[case.description for case in SOURCE_DEFERRAL_CONFLICT_TEST_CASES],
)
def test_given_reuse_from_and_source_deferral_when_planning_then_raises(
    test_case: StandardReuseFromSourceDeferralConflictTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        with pytest.raises(PlannerInputError) as exc_info:
            build_execution_plan(
                project=build_standard_reuse_from_target_project(),
                adapter=adapter,
                connection=connection,
                project_config=ProjectConfig(
                    name="demo",
                    adapter="duckdb",
                    targets={
                        "dev": TargetConfig(
                            schema="dev_schema",
                            reuse_from="prod",
                            defer_sources_to=test_case.target_defer_sources_to,
                        ),
                        "prod": TargetConfig(schema="prod_schema"),
                        "prod_sources": TargetConfig(schema="prod_sources_schema"),
                    },
                ),
                local_config=LocalConfig(),
                defer_sources_to=test_case.defer_sources_to,
            )
    finally:
        adapter.close(connection)

    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        StandardReuseFullRefreshBypassTestCase(
            description="full refresh bypasses standard reuse_from state",
            expected_reuse_from_target_metadata_present=False,
            expected_reuse_decision_metadata_present=False,
        )
    ],
    ids=["full refresh bypasses standard reuse_from state"],
)
def test_given_full_refresh_with_reuse_from_when_planning_then_reuse_state_is_skipped(
    test_case: StandardReuseFullRefreshBypassTestCase,
) -> None:
    adapter: DuckDbAdapter = DuckDbAdapter()
    connection: Any = adapter.connect({"database": ":memory:"})
    try:
        adapter.execute(connection, "CREATE SCHEMA dev_schema")
        plan_output: PlanOutput = build_execution_plan(
            project=build_standard_reuse_from_target_project(),
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
        "standard_reuse_from_target" in plan_output.metadata
    ) is test_case.expected_reuse_from_target_metadata_present
    assert (
        "standard_reuse_decisions" in plan_output.metadata
    ) is test_case.expected_reuse_decision_metadata_present
