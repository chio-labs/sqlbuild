"""Tests for plan output formatting."""

from __future__ import annotations

import json

import pytest

from sqlbuild.cli.output.main.plan import format_plan
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.pipeline.models import PythonPlanEntry
from sqlbuild.compiler.planner.models import (
    CascadeCause,
    CascadeResult,
    CursorBounds,
    CursorInputRelation,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
    SchemaChangeKind,
    WarningSeverity,
)
from sqlbuild.compiler.python_nodes.types import (
    PythonIdentityStatus,
    PythonNodeKind,
    PythonRunPhase,
)
from sqlbuild.presentation.models import DisplayOptions
from sqlbuild.spec.contracts.types import SourceWriteStrategy
from tests.unit.src.sqlbuild.cli.output.main.plan._test_types import (
    FormatPlanColorTestCase,
    FormatPlanTestCase,
)
from tests.unit.src.sqlbuild.cli.output.main.plan.helpers import (
    build_discovered_provider_usage,
    build_function_entry,
    build_model_entry,
    build_plan_output,
    build_plan_provider_usage,
    build_schema_finding,
    build_seed_entry,
    build_source_load_entry,
    build_warning,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FormatPlanTestCase(
            description="changes-only pruned models are visible as current skips",
            plan_output=build_plan_output(
                metadata={"direct_pruned_model_names": ("customer_revenue_check",)}
            ),
            expected_fragments=(
                "Plan ready  0 selected",
                "Skipped current models (1 already up to date)",
            ),
            unexpected_fragments=("customer_revenue_check", "changes-only", "Execution"),
        ),
        FormatPlanTestCase(
            description="verbose changes-only pruned models show current model names",
            plan_output=build_plan_output(
                metadata={"direct_pruned_model_names": ("customer_revenue_check",)}
            ),
            display_options=DisplayOptions(max_entries_per_section=None),
            expected_fragments=(
                "Skipped current models (1 already up to date)",
                "customer_revenue_check",
                "up to date",
            ),
            unexpected_fragments=("changes-only",),
        ),
        FormatPlanTestCase(
            description="source freshness age warnings and errors are visible",
            plan_output=build_plan_output(
                metadata={
                    "direct_source_freshness": {
                        "observed_source_names": ("raw.orders", "raw.payments"),
                        "changed_source_names": (),
                        "unchanged_source_names": ("raw.orders",),
                        "unknown_source_names": (),
                        "age_warning_source_names": ("raw.payments",),
                        "age_error_source_names": ("raw.orders",),
                        "stale_model_names": (),
                        "blocked_model_names": ("fact_orders",),
                    }
                }
            ),
            expected_fragments=(
                "Source freshness",
                "age warnings:",
                "raw.payments",
                "age errors:",
                "raw.orders",
                "source-blocked models:",
                "fact_orders",
            ),
        ),
        FormatPlanTestCase(
            description="direct non-changes-only output hides freshness diagnostics only",
            plan_output=build_plan_output(
                source_load_entries=(build_source_load_entry(name="raw_orders"),),
                warnings=(
                    build_warning(
                        model_name=None,
                        message=(
                            "Stale inputs detected\n\n  Affected selected models:\n    fact_orders"
                        ),
                        code="S302",
                    ),
                    build_warning(
                        model_name="fact_orders",
                        message="schema change requires rebuild",
                    ),
                ),
                metadata={
                    "direct_source_freshness": {
                        "observed_source_names": ("raw_orders",),
                        "changed_source_names": ("raw_orders",),
                        "unchanged_source_names": (),
                        "unknown_source_names": (),
                        "stale_model_names": ("fact_orders",),
                    }
                },
            ),
            include_direct_freshness_diagnostics=False,
            expected_fragments=(
                "Sources to load (1)",
                "raw_orders",
                "Warnings (1)",
                "schema change requires rebuild",
            ),
            unexpected_fragments=(
                "Source freshness",
                "Stale inputs detected",
                "Warnings (2)",
            ),
        ),
        FormatPlanTestCase(
            description="routine models section shows names with strategy and cursor type",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.NO_CHANGE,
                        materialization_type=MaterializationType.VIEW,
                    ),
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.NORMAL_INCREMENTAL,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="timestamp",
                    ),
                    build_model_entry(
                        name="fact_events",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.NORMAL_INCREMENTAL,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="integer",
                        incremental_mode="microbatch",
                    ),
                ),
            ),
            expected_fragments=(
                "Models (3)",
                "stg_orders",
                "fact_orders",
                "fact_events",
                "delete_insert (timestamp)",
                "delete_insert (integer, microbatch)",
                "view",
            ),
            unexpected_fragments=("Normal",),
        ),
        FormatPlanTestCase(
            description="planner-resolved microbatch shows requested and effective work",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_events",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        incremental_mode="microbatch",
                        cursor_column="event_date",
                        cursor_type="timestamp",
                        cursor_grain="day",
                        batch_size="1mo",
                        microbatch_range=CursorBounds(
                            start="2014-01-01",
                            end="2014-04-01",
                        ),
                        start_cursor_override="2014-01-01",
                        end_cursor_override="2014-03-31",
                    ),
                ),
            ),
            expected_fragments=(
                "cursor  event_date (timestamp)",
                "requested  2014-01-01 -> 2014-03-31",
                "range  2014-01-01 \u2192 2014-03-31",
                "grain  day",
                "batch size  1mo",
                "batches  3 x 1mo",
                "bounds  planner-resolved",
            ),
            unexpected_fragments=("resolved at runtime",),
        ),
        FormatPlanTestCase(
            description="runtime-owned microbatch marks range and count as deferred",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="clean_events",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        incremental_mode="microbatch",
                        cursor_column="event_date",
                        cursor_type="timestamp",
                        cursor_grain="day",
                        batch_size="1mo",
                        cursor_input_relations=(
                            CursorInputRelation(
                                relation="stg_events",
                                cursor_column="event_date",
                                cursor_grain="day",
                                is_model_backed=True,
                                is_runtime_produced=True,
                            ),
                        ),
                    ),
                ),
            ),
            expected_fragments=(
                "batches  resolved at runtime after upstream models complete",
                "bounds  runtime-owned (model-backed cursor input)",
            ),
            unexpected_fragments=("batches  3 x", "bounds  planner-resolved"),
        ),
        FormatPlanTestCase(
            description="human plan output omits identity hashes",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.INCREMENTAL,
                        fingerprint_version_hash="expected_hash",
                        previous_version_hash="built_hash",
                    ),
                ),
            ),
            expected_fragments=("Query changed (1)", "fact_orders"),
            unexpected_fragments=("expected_hash", "built_hash", "version_hash"),
        ),
        FormatPlanTestCase(
            description="first run shows materialization label with strategy and microbatch",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.VIEW,
                    ),
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="timestamp",
                        incremental_mode="microbatch",
                    ),
                ),
            ),
            expected_fragments=(
                "First run (2)",
                "stg_orders",
                "view",
                "fact_orders",
                "delete_insert (timestamp, microbatch)",
            ),
        ),
        FormatPlanTestCase(
            description="snapshot models show strategy and historical shape labels",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="customer_current_snapshot",
                        action=PlanAction.SNAPSHOT,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.SNAPSHOT,
                        snapshot_strategy="timestamp",
                    ),
                    build_model_entry(
                        name="customer_daily_snapshot",
                        action=PlanAction.SNAPSHOT,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.SNAPSHOT,
                        snapshot_strategy="check",
                        observed_at_column="observed_at",
                        historical_input="snapshot",
                    ),
                    build_model_entry(
                        name="customer_changes_snapshot",
                        action=PlanAction.SNAPSHOT,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.SNAPSHOT,
                        snapshot_strategy="timestamp",
                        observed_at_column="loaded_at",
                        historical_input="changes",
                    ),
                ),
            ),
            expected_fragments=(
                "First run (3)",
                "customer_current_snapshot",
                "snapshot (timestamp)",
                "customer_daily_snapshot",
                "snapshot (check, historical snapshot)",
                "customer_changes_snapshot",
                "snapshot (timestamp, historical changes)",
            ),
        ),
        FormatPlanTestCase(
            description="query changed shows action policy cursor and mode",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.INCREMENTAL,
                        backfill_action=BackfillAction.BOUNDED,
                        backfill_duration="30d",
                        cursor_column="event_time",
                        cursor_type="timestamp",
                        incremental_mode="microbatch",
                        cursor_bounds=CursorBounds(start="2026-03-26", end="2026-04-25"),
                        previous_query_sql="SELECT order_id FROM raw",
                        query_changed=True,
                    ),
                ),
            ),
            expected_fragments=(
                "Query changed (1)",
                "fact_orders",
                "rebuild last 30d",
                "cursor  event_time",
                "mode  microbatch",
                "2026-03-26",
                "2026-04-24",
                "policy  replay_on_change=bounded-30d",
                "query diff:",
            ),
        ),
        FormatPlanTestCase(
            description="schema changed shows schema diff and policy",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="dim_customers",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.SCHEMA_CHANGED,
                        backfill_action=BackfillAction.BOUNDED,
                        backfill_duration="7d",
                        schema_findings=(
                            build_schema_finding(
                                kind=SchemaChangeKind.COLUMN_ADDED,
                                column_name="discount",
                                expected_type="FLOAT",
                            ),
                        ),
                    ),
                ),
            ),
            expected_fragments=(
                "Schema changed (1)",
                "dim_customers",
                "rebuild last 7d, add column",
                "schema diff:",
                "+ discount",
                "added",
            ),
        ),
        FormatPlanTestCase(
            description="config changed shows config diff without query diff",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.CONFIG_CHANGED,
                        previous_query_sql="SELECT order_id FROM raw",
                        previous_metadata_json=(
                            '{"config":{"materialized":"view"},"model_name":"fact_orders"}'
                        ),
                        fingerprint_metadata_json=(
                            '{"config":{"materialized":"table"},"model_name":"fact_orders"}'
                        ),
                        config_changed=True,
                    ),
                ),
            ),
            expected_fragments=(
                "Config changed (1)",
                "fact_orders",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
            ),
            unexpected_fragments=("query diff:",),
        ),
        FormatPlanTestCase(
            description="query and config changes show both diffs",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.QUERY_CHANGED,
                        previous_query_sql="SELECT order_id FROM raw",
                        previous_metadata_json=(
                            '{"config":{"materialized":"view"},"model_name":"fact_orders"}'
                        ),
                        fingerprint_metadata_json=(
                            '{"config":{"materialized":"table"},"model_name":"fact_orders"}'
                        ),
                        query_changed=True,
                        config_changed=True,
                    ),
                ),
            ),
            expected_fragments=(
                "Query changed (1)",
                "fact_orders",
                "query diff:",
                "config diff:",
                '"materialized": "view"',
                '"materialized": "table"',
            ),
        ),
        FormatPlanTestCase(
            description="full rebuild hides cursor range placeholders",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="hourly_order_activity",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.INCREMENTAL,
                        backfill_action=BackfillAction.FULL,
                        cursor_column="activity_hour",
                        cursor_type="timestamp",
                        incremental_mode="microbatch",
                        cursor_bounds=CursorBounds(
                            start="__SQB_CURSOR_START__",
                            end="__SQB_CURSOR_END__",
                        ),
                        previous_query_sql="SELECT activity_hour FROM raw",
                    ),
                ),
            ),
            expected_fragments=(
                "hourly_order_activity",
                "full rebuild",
                "cursor  activity_hour",
                "mode  microbatch",
            ),
            unexpected_fragments=(
                "range:",
                "__SQB_CURSOR_START__",
                "__SQB_CURSOR_END__",
            ),
        ),
        FormatPlanTestCase(
            description="upstream changed shows cascade cause",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_daily_revenue",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.NORMAL_INCREMENTAL,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_column="event_time",
                        cursor_type="timestamp",
                        backfill_action=BackfillAction.FORWARD_ONLY,
                        cascade=CascadeResult(
                            effective_action=BackfillAction.BOUNDED,
                            effective_duration="90d",
                            root_cause="fact_orders",
                            causes=(
                                CascadeCause(
                                    model_name="fact_orders",
                                    effective_action=BackfillAction.BOUNDED,
                                    effective_duration="90d",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            expected_fragments=(
                "Upstream changed (1)",
                "fact_daily_revenue",
                "rebuild last 90d",
                "cause  fact_orders (90d)",
            ),
            unexpected_fragments=("Normal",),
        ),
        FormatPlanTestCase(
            description="upstream changed with full shows full in cause",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="dim_summary",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.NO_CHANGE,
                        cascade=CascadeResult(
                            effective_action=BackfillAction.FULL,
                            effective_duration=None,
                            root_cause="fact_orders",
                            causes=(
                                CascadeCause(
                                    model_name="fact_orders",
                                    effective_action=BackfillAction.FULL,
                                    effective_duration=None,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            expected_fragments=(
                "Upstream changed (1)",
                "dim_summary",
                "full rebuild",
                "cause  fact_orders (full)",
            ),
        ),
        FormatPlanTestCase(
            description="upstream changed view shows recreate action",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.NO_CHANGE,
                        materialization_type=MaterializationType.VIEW,
                        cascade=CascadeResult(
                            effective_action=BackfillAction.FULL,
                            effective_duration=None,
                            root_cause="raw_orders",
                        ),
                    ),
                ),
            ),
            expected_fragments=("stg_orders", "recreate view"),
            unexpected_fragments=("full rebuild",),
        ),
        FormatPlanTestCase(
            description="seeds section shows seed names",
            plan_output=build_plan_output(
                model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
                seed_entries=(build_seed_entry(name="country_codes"),),
            ),
            expected_fragments=(
                "Seeds (1)",
                "country_codes",
                "first_run",
            ),
        ),
        FormatPlanTestCase(
            description="seeds section shows changed seed reason",
            plan_output=build_plan_output(
                model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
                seed_entries=(
                    build_seed_entry(name="country_codes", reason=PlanReason.CONFIG_CHANGED),
                ),
            ),
            expected_fragments=(
                "Seeds (1)",
                "country_codes  (seed_changed)",
            ),
        ),
        FormatPlanTestCase(
            description="functions section shows names and udf language",
            plan_output=build_plan_output(
                model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
                function_entries=(
                    build_function_entry(name="is_completed_order", language=FunctionLanguage.SQL),
                    build_function_entry(
                        name="is_completed_order_py", language=FunctionLanguage.PYTHON
                    ),
                ),
            ),
            expected_fragments=(
                "Plan ready  3 selected",
                "Functions (2)",
                "is_completed_order",
                "sql udf",
                "is_completed_order_py",
                "python udf",
            ),
        ),
        FormatPlanTestCase(
            description="header includes source loads when sources will load",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(name="stg_orders", action=PlanAction.CREATE_TABLE),
                ),
                source_load_entries=(build_source_load_entry(name="raw_orders"),),
            ),
            expected_fragments=(
                "Plan ready  1 selected, 1 source to load",
                "Sources to load (1)",
                "raw_orders",
            ),
        ),
        FormatPlanTestCase(
            description="plan shows python lifecycle sections",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(name="fact_orders", action=PlanAction.CREATE_TABLE),
                ),
                source_load_entries=(build_source_load_entry(name="raw_orders"),),
            ),
            python_plan_entries=(
                PythonPlanEntry(
                    name="prepare_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                ),
                PythonPlanEntry(
                    name="publish_orders",
                    kind=PythonNodeKind.ASSET,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                ),
                PythonPlanEntry(
                    name="profile_fact_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.READ_SIDE,
                ),
            ),
            expected_fragments=(
                "Plan ready  1 selected, 1 source to load, 3 Python nodes",
                "Python ingress (2)",
                "prepare_orders",
                "task",
                "publish_orders",
                "asset",
                "Python read-side (1)",
                "profile_fact_orders",
            ),
            expected_ordered_fragments=(
                "Python ingress (2)",
                "Sources to load (1)",
                "First run (1)",
                "Python read-side (1)",
            ),
        ),
        FormatPlanTestCase(
            description="changed python identity shows source and dependency diffs",
            plan_output=build_plan_output(),
            python_plan_entries=(
                PythonPlanEntry(
                    name="prepare_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                    identity_status=PythonIdentityStatus.CHANGED,
                    previous_definition_json=json.dumps(
                        {"source_text": "def prepare_orders(ctx):\n    return 1\n"},
                        sort_keys=True,
                    ),
                    current_definition_json=json.dumps(
                        {"source_text": "def prepare_orders(ctx):\n    return 2\n"},
                        sort_keys=True,
                    ),
                    previous_metadata_json=json.dumps(
                        {
                            "dependencies": [
                                {
                                    "module": "tasks.helpers",
                                    "qualname": "order_label",
                                    "source_path": "tasks/helpers.py",
                                    "source_text": "def order_label():\n    return 'old'\n",
                                }
                            ]
                        },
                        sort_keys=True,
                    ),
                    current_metadata_json=json.dumps(
                        {
                            "dependencies": [
                                {
                                    "module": "tasks.helpers",
                                    "qualname": "order_label",
                                    "source_path": "tasks/helpers.py",
                                    "source_text": "def order_label():\n    return 'new'\n",
                                }
                            ]
                        },
                        sort_keys=True,
                    ),
                ),
            ),
            expected_fragments=(
                "Python ingress (1)",
                "prepare_orders",
                "task (changed)",
                "python diff:",
                "source diff:",
                "dependency diff:",
                "-    return 1",
                "+    return 2",
                "tasks/helpers.py :: tasks.helpers :: order_label",
                "-    return 'old'",
                "+    return 'new'",
            ),
        ),
        FormatPlanTestCase(
            description="header includes source reloads when sources will reload",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(name="stg_orders", action=PlanAction.CREATE_TABLE),
                ),
                source_load_entries=(build_source_load_entry(name="raw_orders", is_reload=True),),
            ),
            full_refresh=True,
            expected_fragments=(
                "Plan ready  1 selected, 1 source to reload",
                "Sources to reload (1)",
                "raw_orders",
            ),
        ),
        FormatPlanTestCase(
            description="source load section formats strategy details",
            plan_output=build_plan_output(
                source_load_entries=(
                    build_source_load_entry(
                        name="raw_events",
                        write_strategy=SourceWriteStrategy.DELETE_INSERT,
                        cursor_column="event_at",
                    ),
                    build_source_load_entry(
                        name="raw_orders",
                        write_strategy=SourceWriteStrategy.MERGE,
                        unique_key=("order_id", "updated_at"),
                    ),
                    build_source_load_entry(
                        name="raw_ingestr",
                        write_strategy=None,
                        integration_kind="ingestr",
                    ),
                    build_source_load_entry(name="raw_self_managed", write_strategy=None),
                ),
            ),
            expected_fragments=(
                "Plan ready  0 selected, 4 sources to load",
                "raw_events",
                "delete_insert (cursor: event_at)",
                "raw_orders",
                "merge (unique_key: order_id, updated_at)",
                "raw_ingestr",
                "external (ingestr)",
                "raw_self_managed",
                "self-managed",
            ),
        ),
        FormatPlanTestCase(
            description="function query change shows diff and policy",
            plan_output=build_plan_output(
                model_entries=(build_model_entry(name="orders", action=PlanAction.CREATE_TABLE),),
                function_entries=(
                    build_function_entry(
                        name="is_completed_order",
                        language=FunctionLanguage.SQL,
                        reason=PlanReason.QUERY_CHANGED,
                        backfill_action=BackfillAction.FULL,
                        previous_query_sql="returns=BOOLEAN\nbody=\norder_status = 'completed'",
                    ),
                ),
            ),
            expected_fragments=(
                "Changed functions (1)",
                "is_completed_order",
                "sql udf",
                "policy  replay_on_change=full",
                "query diff:",
                "--- previous",
                "+++ current",
            ),
        ),
        FormatPlanTestCase(
            description="upstream changed prefers root function changed cause",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="daily_activity_rollup",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.NO_CHANGE,
                        cascade=CascadeResult(
                            effective_action=BackfillAction.FULL,
                            effective_duration=None,
                            root_cause="is_completed_order",
                            root_reason=PlanReason.FUNCTION_CHANGED,
                            causes=(
                                CascadeCause(
                                    model_name="hourly_order_activity",
                                    effective_action=BackfillAction.FULL,
                                    effective_duration=None,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            expected_fragments=(
                "Upstream changed (1)",
                "daily_activity_rollup",
                "full rebuild",
                "cause  is_completed_order (function changed)",
            ),
            unexpected_fragments=(
                "cause  hourly_order_activity",
                "cause  is_completed_order (full)",
            ),
        ),
        FormatPlanTestCase(
            description="warnings section shows warning messages",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="orders",
                        action=PlanAction.SKIP,
                        reason=PlanReason.NO_CHANGE,
                        backfill_action=BackfillAction.FORWARD_ONLY,
                    ),
                ),
                warnings=(
                    build_warning(
                        model_name="stg_customers",
                        message="type change detected",
                        severity=WarningSeverity.WARNING,
                    ),
                ),
            ),
            expected_fragments=(
                "Warnings (1)",
                "stg_customers",
                "type change detected",
            ),
        ),
        FormatPlanTestCase(
            description="multiline warning messages terminate their child tree",
            plan_output=build_plan_output(
                warnings=(
                    build_warning(
                        model_name="stg_customers",
                        message="type change detected\nrebuild required",
                        severity=WarningSeverity.WARNING,
                    ),
                ),
            ),
            expected_fragments=(
                "├── type change detected",
                "└── rebuild required",
            ),
        ),
        FormatPlanTestCase(
            description="full refresh shows aggregate counts with incremental detail",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.FULL_REFRESH,
                        materialization_type=MaterializationType.VIEW,
                    ),
                    build_model_entry(
                        name="dim_customers",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.FULL_REFRESH,
                    ),
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.FULL_REFRESH,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="timestamp",
                        incremental_mode="microbatch",
                    ),
                ),
            ),
            full_refresh=True,
            expected_fragments=(
                "Plan ready  full refresh, 3 selected",
                "Full refresh (3)",
                "view",
                "table",
                "delete_insert (timestamp, microbatch)",
            ),
            unexpected_fragments=("Normal", "Query changed", "First run"),
        ),
        FormatPlanTestCase(
            description="empty plan shows only header and selected zero",
            plan_output=build_plan_output(),
            expected_fragments=("Plan ready  0 selected",),
            unexpected_fragments=("Normal", "Seeds", "Warnings"),
        ),
        FormatPlanTestCase(
            description="non-microbatch incremental omits mode line",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.INCREMENTAL,
                        backfill_action=BackfillAction.BOUNDED,
                        backfill_duration="30d",
                        cursor_column="event_time",
                        cursor_type="timestamp",
                    ),
                ),
            ),
            expected_fragments=("cursor  event_time",),
            unexpected_fragments=("mode:",),
        ),
        FormatPlanTestCase(
            description="custom materialization shows name with custom suffix in normal section",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CUSTOM,
                        reason=PlanReason.NO_CHANGE,
                        materialization_type=MaterializationType.CUSTOM,
                        custom_materialization_name="partition_tracked",
                    ),
                ),
            ),
            expected_fragments=("partition_tracked (custom)",),
        ),
        FormatPlanTestCase(
            description="custom materialization shows name with custom suffix in first run section",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CUSTOM,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.CUSTOM,
                        custom_materialization_name="atomic_swap",
                    ),
                ),
            ),
            expected_fragments=("atomic_swap (custom)",),
        ),
        FormatPlanTestCase(
            description="changed sections appear before routine resource sections",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.QUERY_CHANGED,
                        backfill_action=BackfillAction.FULL,
                        previous_query_sql="SELECT order_id FROM raw",
                    ),
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.NO_CHANGE,
                        materialization_type=MaterializationType.VIEW,
                    ),
                ),
                function_entries=(
                    build_function_entry(name="is_completed_order"),
                    build_function_entry(
                        name="normalize_email",
                        reason=PlanReason.QUERY_CHANGED,
                        backfill_action=BackfillAction.FULL,
                        previous_query_sql="returns=TEXT\nbody=old_email",
                    ),
                ),
                seed_entries=(build_seed_entry(name="waffle_types"),),
            ),
            expected_fragments=(
                "normalize_email",
                "is_completed_order",
                "fact_orders",
                "stg_orders",
                "waffle_types",
            ),
            unexpected_fragments=("Functions (2", "Models (2"),
            expected_ordered_fragments=(
                "Changed functions (1)",
                "Query changed (1)",
                "Models (1)",
                "Functions (1)",
                "Seeds (1)",
            ),
        ),
        FormatPlanTestCase(
            description="detail rows align value column to longest displayed name",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="hourly_activity_with_daily_context",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="timestamp",
                        incremental_mode="microbatch",
                    ),
                    build_model_entry(
                        name="order_status_index",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.FIRST_RUN,
                        materialization_type=MaterializationType.INCREMENTAL,
                        incremental_strategy="delete_insert",
                        cursor_type="integer",
                    ),
                ),
            ),
            expected_fragments=(
                "\u251c\u2500\u2500 hourly_activity_with_daily_context "
                "delete_insert (timestamp, microbatch)",
                "\u2514\u2500\u2500 order_status_index                 delete_insert (integer)",
            ),
        ),
        FormatPlanTestCase(
            description="virtual metadata explains status and caps affected model list",
            plan_output=build_plan_output(
                metadata={
                    "virtual_environment_name": "dev",
                    "virtual_environment_status": "working",
                    "virtual_stale_root_names": ("model_00", "model_01"),
                    "virtual_stale_model_names": tuple(f"model_{index:02d}" for index in range(55)),
                },
            ),
            expected_fragments=(
                "Virtual environment  dev (working, build required)",
                "Models needing build (55)",
                "directly affected (2)  model_00, model_01",
                "downstream affected (53)  model_02",
                "... (+33 more; use --verbose to show all)",
            ),
            expected_ordered_fragments=(
                "Models needing build (55)",
                "directly affected (2)  model_00, model_01",
                "downstream affected (53)  model_02",
            ),
        ),
        FormatPlanTestCase(
            description="virtual metadata shows full affected sets in verbose output",
            plan_output=build_plan_output(
                metadata={
                    "virtual_environment_name": "dev",
                    "virtual_environment_status": "working",
                    "virtual_stale_root_names": ("model_00",),
                    "virtual_stale_model_names": tuple(f"model_{index:02d}" for index in range(3)),
                },
            ),
            display_options=DisplayOptions(max_entries_per_section=None),
            expected_fragments=(
                "directly affected (1)  model_00",
                "downstream affected (2)  model_01, model_02",
            ),
            unexpected_fragments=("use --verbose",),
        ),
        FormatPlanTestCase(
            description="virtual metadata shows models outside partial selection",
            plan_output=build_plan_output(
                metadata={
                    "virtual_environment_name": "dev",
                    "virtual_environment_status": "working",
                    "virtual_stale_root_names": ("stg_orders",),
                    "virtual_stale_model_names": ("fact_orders", "orders_rollup", "stg_orders"),
                    "virtual_remaining_stale_model_names": ("orders_rollup",),
                },
            ),
            expected_fragments=(
                "Models needing build (3)",
                "directly affected (1)  stg_orders",
                "downstream affected (2)  fact_orders, orders_rollup",
                "outside this plan (1)  orders_rollup",
            ),
            expected_ordered_fragments=(
                "directly affected (1)  stg_orders",
                "downstream affected (2)  fact_orders, orders_rollup",
                "outside this plan (1)  orders_rollup",
            ),
        ),
        FormatPlanTestCase(
            description="virtual metadata explains source freshness outcomes",
            plan_output=build_plan_output(
                metadata={
                    "virtual_environment_name": "dev",
                    "virtual_environment_status": "working",
                    "virtual_stale_root_names": ("fact_orders",),
                    "virtual_stale_model_names": ("fact_orders", "orders_rollup"),
                    "virtual_source_freshness_observed_source_names": (
                        "raw_customers",
                        "raw_orders",
                    ),
                    "virtual_source_freshness_unchanged_source_names": ("raw_customers",),
                    "virtual_source_freshness_incomplete_source_names": ("raw_payments",),
                    "virtual_source_freshness_incomplete_model_names": ("fact_payments",),
                },
            ),
            expected_fragments=(
                "Source freshness (2 of 3 checked)",
                "new or changed (1)  raw_orders",
                "unchanged (1)  raw_customers",
                "not verifiable (1)  raw_payments",
                "affected models (1)  fact_payments",
                "Models needing build (2)",
                "directly affected (1)  fact_orders",
                "downstream affected (1)  orders_rollup",
            ),
            unexpected_fragments=("source freshness observed", "stale model set"),
        ),
        FormatPlanTestCase(
            description="direct metadata caps remaining stale models after partial selection",
            plan_output=build_plan_output(
                metadata={
                    "direct_remaining_stale_model_names": tuple(
                        f"model_{index:02d}" for index in range(55)
                    ),
                },
            ),
            expected_fragments=(
                "Remaining stale",
                "models outside selection: 55",
                "model set: model_00",
                "... (+35 more; use --verbose to show all)",
            ),
        ),
        FormatPlanTestCase(
            description="direct metadata shows full remaining stale set in verbose output",
            plan_output=build_plan_output(
                metadata={
                    "direct_remaining_stale_model_names": tuple(
                        f"model_{index:02d}" for index in range(3)
                    ),
                },
            ),
            display_options=DisplayOptions(max_entries_per_section=None),
            expected_fragments=("model set: model_00, model_01, model_02",),
            unexpected_fragments=("use --verbose",),
        ),
        FormatPlanTestCase(
            description="provider usages show compact selected Python surface counts",
            plan_output=build_plan_output(
                provider_usages=(
                    build_plan_provider_usage(
                        provider_name="marker_provider",
                        consumer_kind="loader",
                        consumer_name="raw_orders",
                    ),
                    build_plan_provider_usage(
                        provider_name="marker_provider",
                        consumer_kind="hook",
                        consumer_name="mark_pre",
                    ),
                ),
            ),
            python_plan_entries=(
                PythonPlanEntry(
                    name="publish_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.READ_SIDE,
                    provider_usages=(build_discovered_provider_usage(),),
                ),
            ),
            expected_fragments=(
                "Providers",
                "marker_provider  used by 3 selected Python surfaces",
            ),
        ),
        FormatPlanTestCase(
            description="provider usages show verbose selected Python surface details",
            plan_output=build_plan_output(
                provider_usages=(
                    build_plan_provider_usage(
                        provider_name="marker_provider",
                        consumer_kind="loader",
                        consumer_name="raw_orders",
                    ),
                    build_plan_provider_usage(
                        provider_name="marker_provider",
                        consumer_kind="hook",
                        consumer_name="mark_pre",
                    ),
                ),
            ),
            display_options=DisplayOptions(max_entries_per_section=None),
            python_plan_entries=(
                PythonPlanEntry(
                    name="publish_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.READ_SIDE,
                    provider_usages=(build_discovered_provider_usage(),),
                ),
            ),
            expected_fragments=(
                "Providers",
                "\u2514\u2500\u2500 marker_provider",
                "    ├── hook mark_pre (MarkerProvider)",
                "    ├── loader raw_orders (MarkerProvider)",
                "    └── task publish_orders (MarkerProvider)",
            ),
            unexpected_fragments=("used by 3 selected Python surfaces", "parameter"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_plan_output_when_formatting_then_contains_expected_fragments(
    test_case: FormatPlanTestCase,
) -> None:
    result: str = format_plan(
        plan=test_case.plan_output,
        full_refresh=test_case.full_refresh,
        use_color=False,
        display_options=test_case.display_options,
        include_direct_freshness_diagnostics=(test_case.include_direct_freshness_diagnostics),
        python_plan_entries=test_case.python_plan_entries,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
    for fragment in test_case.unexpected_fragments:
        assert fragment not in result, f"Did not expect '{fragment}' in output:\n{result}"
    previous_index: int = -1
    for fragment in test_case.expected_ordered_fragments:
        current_index: int = result.index(fragment)
        assert current_index > previous_index, result
        previous_index = current_index


@pytest.mark.parametrize(
    "test_case",
    [
        FormatPlanColorTestCase(
            description="styles header names warnings and diffs semantically",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="dim_customers",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.SCHEMA_CHANGED,
                        schema_findings=(
                            build_schema_finding(
                                kind=SchemaChangeKind.COLUMN_ADDED,
                                column_name="discount",
                                expected_type="FLOAT",
                            ),
                        ),
                        previous_query_sql="SELECT old_column FROM raw",
                    ),
                ),
                warnings=(
                    build_warning(
                        model_name="dim_customers",
                        message="schema change requires rebuild",
                        severity=WarningSeverity.WARNING,
                    ),
                ),
            ),
            expected_fragments=(
                "\033[34m\033[1mPlan ready\033[0m  \033[2m1 selected\033[0m",
                "dim_customers",
                "\033[32m      + discount  FLOAT   (added)\033[0m",
                "\033[33m\033[1mWarnings (1)\033[0m",
                "\033[2m\u2514\u2500\u2500\033[0m dim_customers",
                "    \033[2m\u2514\u2500\u2500\033[0m \033[33mschema change requires rebuild\033[0m",
            ),
        ),
        FormatPlanColorTestCase(
            description="styles provider names and consumers semantically",
            plan_output=build_plan_output(
                provider_usages=(
                    build_plan_provider_usage(
                        provider_name="marker_provider",
                        consumer_kind="loader",
                        consumer_name="raw_orders",
                    ),
                ),
            ),
            expected_fragments=(
                "marker_provider",
                "\033[2mused by 1 selected Python surface\033[0m",
            ),
        ),
        FormatPlanColorTestCase(
            description="styles source freshness and diff metadata semantically",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="fact_orders",
                        action=PlanAction.CREATE_TABLE,
                        reason=PlanReason.QUERY_CHANGED,
                        previous_query_sql="SELECT old_amount FROM raw_orders",
                        query_changed=True,
                    ),
                ),
                metadata={
                    "direct_source_freshness": {
                        "observed_source_names": ("raw_orders",),
                        "changed_source_names": ("raw_orders",),
                        "unchanged_source_names": (),
                        "unknown_source_names": (),
                        "stale_model_names": ("fact_orders",),
                    }
                },
            ),
            expected_fragments=(
                "\033[2mobserved:\033[0m 1",
                "\033[2mobserved set:\033[0m raw_orders",
                "\033[2mchanged:\033[0m \033[33m1\033[0m",
                "\033[2mchanged set:\033[0m \033[33mraw_orders\033[0m",
                "\033[2munchanged:\033[0m \033[2m0\033[0m",
                "\033[2msource-stale models:\033[0m \033[33mfact_orders\033[0m",
                "\033[2mquery diff:\033[0m",
                "\033[2m      --- previous\033[0m",
                "\033[2m      +++ current\033[0m",
                "\033[2m      @@",
            ),
        ),
        FormatPlanColorTestCase(
            description="dims routine kinds and accents changed view actions",
            plan_output=build_plan_output(
                model_entries=(
                    build_model_entry(
                        name="stg_orders",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.NO_CHANGE,
                        materialization_type=MaterializationType.VIEW,
                    ),
                    build_model_entry(
                        name="stg_payments",
                        action=PlanAction.CREATE_VIEW,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.VIEW,
                        backfill_action=BackfillAction.FORWARD_ONLY,
                        previous_query_sql="SELECT payment_id FROM raw_payments",
                    ),
                    build_model_entry(
                        name="fact_payments",
                        action=PlanAction.INCREMENTAL_DELETE_INSERT,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.INCREMENTAL,
                        backfill_action=BackfillAction.FORWARD_ONLY,
                        previous_query_sql="SELECT payment_id FROM stg_payments",
                    ),
                    build_model_entry(
                        name="partitioned_payments",
                        action=PlanAction.CUSTOM,
                        reason=PlanReason.QUERY_CHANGED,
                        materialization_type=MaterializationType.CUSTOM,
                        backfill_action=BackfillAction.FORWARD_ONLY,
                        custom_materialization_name="partition_tracked",
                        previous_query_sql="SELECT payment_id FROM stg_payments",
                    ),
                ),
            ),
            expected_fragments=(
                "stg_orders",
                "\033[2mview\033[0m",
                "stg_payments",
                "\033[34mrecreate view\033[0m",
                "fact_payments",
                "\033[34mcontinue forward\033[0m",
                "partitioned_payments",
                "\033[34mrun partition_tracked\033[0m",
            ),
        ),
        FormatPlanColorTestCase(
            description="styles python dependency diff headers as metadata",
            plan_output=build_plan_output(),
            python_plan_entries=(
                PythonPlanEntry(
                    name="prepare_orders",
                    kind=PythonNodeKind.TASK,
                    phase=PythonRunPhase.PRE_SQL_INGRESS,
                    identity_status=PythonIdentityStatus.CHANGED,
                    previous_metadata_json=json.dumps(
                        {
                            "dependencies": [
                                {
                                    "module": "tasks.helpers",
                                    "qualname": "order_label",
                                    "source_path": "tasks/helpers.py",
                                    "source_text": "def order_label():\n    return 'old'\n",
                                }
                            ]
                        },
                        sort_keys=True,
                    ),
                    current_metadata_json=json.dumps(
                        {
                            "dependencies": [
                                {
                                    "module": "tasks.helpers",
                                    "qualname": "order_label",
                                    "source_path": "tasks/helpers.py",
                                    "source_text": "def order_label():\n    return 'new'\n",
                                }
                            ]
                        },
                        sort_keys=True,
                    ),
                ),
            ),
            expected_fragments=(
                "\033[2m         # tasks/helpers.py :: tasks.helpers :: order_label\033[0m",
                "\033[38;5;167m      -    return 'old'\033[0m",
                "\033[32m      +    return 'new'\033[0m",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_plan_output_when_formatting_with_color_then_styles_semantic_parts(
    test_case: FormatPlanColorTestCase,
) -> None:
    result: str = format_plan(
        plan=test_case.plan_output,
        use_color=True,
        python_plan_entries=test_case.python_plan_entries,
    )

    for fragment in test_case.expected_fragments:
        assert fragment in result, f"Expected '{fragment}' in output:\n{result}"
