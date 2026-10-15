//! The layouts of every native record class.

use crate::bindings::_helpers::records::models::{FieldDefault, FieldSpec, RecordSpec};

pub(crate) const NATIVE_MODULE: &str = "sqlbuild._native";
/// The class attribute holding a record class's index into `RECORDS`.
pub(crate) const RECORD_SPEC_ATTRIBUTE: &str = "__native_record__";
pub(crate) const FROZEN_INSTANCE_ERROR: (&str, &str) = ("dataclasses", "FrozenInstanceError");
pub(crate) const DATACLASSES_MODULE: &str = "dataclasses";
pub(crate) const DATACLASS_FIELDS_ATTRIBUTE: &str = "__dataclass_fields__";
/// The marker `dataclasses` gives ordinary (not class or init-only) fields.
pub(crate) const DATACLASS_FIELD_KIND: &str = "_FIELD";

/// Every native record group, in registration order.
pub(crate) const RECORDS: &[&[RecordSpec]] = &[
    COMMAND_RECORDS,
    ENTRY_RECORDS,
    OUTPUT_RECORDS,
    COMPILE_RECORDS,
];

const NESTED_PROGRESS_CHILD_ROW: RecordSpec = RecordSpec {
    name: "NestedProgressChildRow",
    doc: "One child row rendered below a completed nested progress item.",
    fields: &[
        FieldSpec::required("label"),
        FieldSpec::required("name"),
        FieldSpec::required("status_text"),
        FieldSpec::new("detail", FieldDefault::Text("")),
    ],
};
const AUDIT_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "AuditCommandRequest",
    doc: "CLI inputs for one audit command invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("defer_to", FieldDefault::None),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
    ],
};
const AUDIT_INVOCATION: RecordSpec = RecordSpec {
    name: "AuditInvocation",
    doc: "Resolved project, adapter, and reporter context for the audit command.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("use_color"),
        FieldSpec::required("progress_stream"),
        FieldSpec::required("connection_progress"),
        FieldSpec::required("planning_progress"),
    ],
};
const BUILD_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "BuildCommandRequest",
    doc: "CLI inputs for one build command invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("defer_to", FieldDefault::None),
        FieldSpec::new("defer_clone_from", FieldDefault::None),
        FieldSpec::new("defer_sources_to", FieldDefault::None),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("fail_fast", FieldDefault::False),
        FieldSpec::new("full_refresh", FieldDefault::False),
        FieldSpec::new("load_sources", FieldDefault::None),
        FieldSpec::new("reload_sources", FieldDefault::False),
        FieldSpec::new("include_python", FieldDefault::True),
        FieldSpec::new("allow_snapshot_full_refresh", FieldDefault::False),
        FieldSpec::new("allow_table_type_downgrade", FieldDefault::False),
        FieldSpec::new("allow_retention_decrease", FieldDefault::False),
        FieldSpec::new("allow_missing_migration_origin", FieldDefault::False),
        FieldSpec::new("allow_snapshot_schema_change", FieldDefault::False),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("verbose", FieldDefault::False),
        FieldSpec::new("debug", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("run_tests", FieldDefault::True),
        FieldSpec::new("run_audits", FieldDefault::True),
        FieldSpec::new("manifest", FieldDefault::False),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
        FieldSpec::new("event_output_path", FieldDefault::None),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec::new("max_microbatches", FieldDefault::None),
        FieldSpec::new("selection_diagnostics", FieldDefault::False),
        FieldSpec::new("selector_files", FieldDefault::EmptyTuple),
    ],
};
const BUILD_INVOCATION: RecordSpec = RecordSpec {
    name: "BuildInvocation",
    doc: "Resolved project, adapter, and reporter context for the build command.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("effective_defer_clone_from"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("use_color"),
        FieldSpec::required("progress_stream"),
        FieldSpec::required("connection_progress"),
        FieldSpec::required("planning_progress"),
        FieldSpec::required("should_load_sources"),
        FieldSpec::new("effective_target_name", FieldDefault::None),
        FieldSpec::new(
            "execution_limits",
            FieldDefault::Call("sqlbuild.spec.contracts.models", "ExecutionLimitsConfig"),
        ),
    ],
};
const CHECK_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "CheckCommandRequest",
    doc: "CLI inputs for one check command invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
    ],
};
const CHECK_INVOCATION: RecordSpec = RecordSpec {
    name: "CheckInvocation",
    doc: "Resolved project, adapter, and reporter context for the check command.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("use_color"),
        FieldSpec::required("progress_stream"),
        FieldSpec::required("connection_progress"),
        FieldSpec::required("planning_progress"),
    ],
};
const CLONE_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "CloneCommandRequest",
    doc: "CLI inputs for one clone command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("no_color"),
        FieldSpec::required("no_sql_validation"),
        FieldSpec::required("origin_target_name"),
        FieldSpec::required("destination_target_name"),
        FieldSpec::required("hard_copy"),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("verbose", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output_path", FieldDefault::None),
        FieldSpec::new("event_output_path", FieldDefault::None),
    ],
};
const DBT_SQLBUILD_WORK_CONTEXT: RecordSpec = RecordSpec {
    name: "DbtSqlbuildWorkContext",
    doc: "Shared execution context for one dbt interop SQLBuild work run.",
    fields: &[
        FieldSpec::required("plan_output"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("adapter"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("output_stream"),
        FieldSpec::required("use_color"),
        FieldSpec::required("snapshots_config"),
        FieldSpec::required("execution_limits"),
    ],
};
const PLAN_SAFETY_GATES: RecordSpec = RecordSpec {
    name: "PlanSafetyGates",
    doc: "Pre-confirmed plan safety gates and the guidance shown when one needs a terminal.",
    fields: &[
        FieldSpec::required("allow_missing_migration_origin"),
        FieldSpec::required("allow_snapshot_full_refresh"),
        FieldSpec::required("allow_table_type_downgrade"),
        FieldSpec::required("allow_retention_decrease"),
        FieldSpec::required("missing_origin_help"),
        FieldSpec::required("snapshot_full_refresh_help"),
        FieldSpec::required("table_type_downgrade_help"),
        FieldSpec::required("retention_decrease_help"),
        FieldSpec::required("execution_limit_note"),
    ],
};
const DBT_INIT_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "DbtInitCommandRequest",
    doc: "CLI inputs for one dbt init command invocation.",
    fields: &[
        FieldSpec::required("cwd"),
        FieldSpec::required("dbt_project_dir"),
        FieldSpec::required("profiles_dir"),
        FieldSpec::required("profile_name"),
        FieldSpec::required("target_name"),
        FieldSpec::required("sqb_output_dir"),
        FieldSpec::required("dry_run"),
        FieldSpec::required("overwrite"),
        FieldSpec::required("skip_dbt_debug"),
    ],
};
const DIFF_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "DiffCommandRequest",
    doc: "CLI inputs for one diff command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("no_color"),
        FieldSpec::required("no_sql_validation"),
        FieldSpec::required("from_name"),
        FieldSpec::required("to_name"),
        FieldSpec::required("full"),
        FieldSpec::required("schema_only"),
        FieldSpec::required("bounded"),
        FieldSpec::new("max_column_examples", FieldDefault::None),
        FieldSpec::new("max_row_only_examples", FieldDefault::None),
        FieldSpec::new("sample_rows", FieldDefault::None),
        FieldSpec::new("sample_seed", FieldDefault::None),
        FieldSpec::new("exhaustive", FieldDefault::False),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
        FieldSpec::new("max_models", FieldDefault::None),
        FieldSpec::new("max_columns", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("verbose", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("left_query", FieldDefault::None),
        FieldSpec::new("left_query_file", FieldDefault::None),
        FieldSpec::new("left_label", FieldDefault::None),
        FieldSpec::new("right_query", FieldDefault::None),
        FieldSpec::new("right_query_file", FieldDefault::None),
        FieldSpec::new("right_label", FieldDefault::None),
        FieldSpec::new("unique_key_override", FieldDefault::EmptyTuple),
        FieldSpec::new("unkeyed", FieldDefault::False),
        FieldSpec::new("excluded_columns_override", FieldDefault::EmptyTuple),
        FieldSpec::new("tolerance_overrides", FieldDefault::EmptyTuple),
        FieldSpec::new("max_value_length", FieldDefault::None),
        FieldSpec::new("suppress_example_values", FieldDefault::False),
        FieldSpec::new("full_example_values", FieldDefault::False),
    ],
};
const QUERY_DIFF_PREPARATION: RecordSpec = RecordSpec {
    name: "QueryDiffPreparation",
    doc: "Resolved raw-query diff adapter, connection, SQL, and limits.",
    fields: &[
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("left_sql"),
        FieldSpec::required("right_sql"),
        FieldSpec::required("left_label"),
        FieldSpec::required("right_label"),
        FieldSpec::required("selected_target"),
        FieldSpec::required("database"),
        FieldSpec::required("schema"),
        FieldSpec::required("run_id"),
        FieldSpec::required("artifact_ttl"),
        FieldSpec::required("effective_max_column_examples"),
        FieldSpec::required("effective_max_row_only_examples"),
    ],
};
const FRESHNESS_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "FreshnessCommandRequest",
    doc: "CLI inputs for one `sqb freshness` invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
        FieldSpec::new("fail_on_error", FieldDefault::False),
        FieldSpec::new("compare_state", FieldDefault::False),
        FieldSpec::new("fail_on_stale", FieldDefault::False),
    ],
};
const JANITOR_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "JanitorCommandRequest",
    doc: "CLI inputs for one janitor command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("auto_approve", FieldDefault::False),
        FieldSpec::new("retention_days", FieldDefault::None),
        FieldSpec::new("direct_state_history_versions", FieldDefault::None),
        FieldSpec::new("drop_old_name_views", FieldDefault::EmptyTuple),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("as_target", FieldDefault::None),
    ],
};
const JANITOR_INVOCATION: RecordSpec = RecordSpec {
    name: "JanitorInvocation",
    doc: "Resolved project discovery and output context for janitor.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("use_color"),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("active_target_name", FieldDefault::None),
        FieldSpec::new("as_target", FieldDefault::None),
    ],
};
const JANITOR_SETTINGS: RecordSpec = RecordSpec {
    name: "JanitorSettings",
    doc: "Validated effective janitor settings.",
    fields: &[
        FieldSpec::required("retention_days"),
        FieldSpec::required("direct_state_history_versions"),
        FieldSpec::new("archive_retention_days", FieldDefault::Int(14)),
        FieldSpec::new("drop_old_name_views", FieldDefault::EmptyTuple),
    ],
};
const LOAD_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "LoadCommandRequest",
    doc: "CLI inputs for one load command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("reload", FieldDefault::False),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
    ],
};
const PLAN_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "PlanCommandRequest",
    doc: "CLI inputs for one plan command invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("defer_to", FieldDefault::None),
        FieldSpec::new("defer_sources_to", FieldDefault::None),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("as_target", FieldDefault::None),
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("full_refresh", FieldDefault::False),
        FieldSpec::new("load_sources", FieldDefault::None),
        FieldSpec::new("include_python", FieldDefault::True),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("verbose", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec::new("max_microbatches", FieldDefault::None),
        FieldSpec::new("selection_diagnostics", FieldDefault::False),
    ],
};
const PLAYGROUND_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "PlaygroundCommandRequest",
    doc: "CLI inputs for one playground command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("target_path"),
        FieldSpec::new("template", FieldDefault::Text("waffle_shop")),
    ],
};
const ADAPTER_CONNECTION_CONTEXT: RecordSpec = RecordSpec {
    name: "AdapterConnectionContext",
    doc: "Resolved adapter and connection configuration for one CLI command.",
    fields: &[
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
    ],
};
const SCENARIO_SNAPSHOT_LIMIT_INPUTS: RecordSpec = RecordSpec {
    name: "ScenarioSnapshotLimitInputs",
    doc: "CLI snapshot capture-limit overrides for one scenario run.",
    fields: &[
        FieldSpec::new("max_snapshot_rows", FieldDefault::None),
        FieldSpec::new("max_snapshot_total_rows", FieldDefault::None),
        FieldSpec::new("max_snapshot_bytes", FieldDefault::None),
        FieldSpec::new("max_snapshot_total_bytes", FieldDefault::None),
        FieldSpec::new("force", FieldDefault::False),
    ],
};
const SCENARIO_TEST_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "ScenarioTestCommandRequest",
    doc: "CLI inputs for one `sqb scenario test` invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("scenario_namespace", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selectors", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("retain", FieldDefault::False),
        FieldSpec::new("local", FieldDefault::False),
        FieldSpec::new("strict", FieldDefault::False),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("sync_snapshots", FieldDefault::False),
        FieldSpec::new("refresh", FieldDefault::False),
        FieldSpec::new(
            "limit_inputs",
            FieldDefault::Call("sqlbuild._native", "ScenarioSnapshotLimitInputs"),
        ),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
    ],
};
const SCENARIO_CAPTURE_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "ScenarioCaptureCommandRequest",
    doc: "CLI inputs for one `sqb scenario capture` invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("scenario_namespace", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selectors", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("retain", FieldDefault::False),
        FieldSpec::new(
            "limit_inputs",
            FieldDefault::Call("sqlbuild._native", "ScenarioSnapshotLimitInputs"),
        ),
    ],
};
const SEED_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "SeedCommandRequest",
    doc: "CLI inputs for one seed command invocation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
    ],
};
const SEED_INVOCATION: RecordSpec = RecordSpec {
    name: "SeedInvocation",
    doc: "Resolved project, adapter, connection, and output context for seed.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("use_color"),
        FieldSpec::required("progress_stream"),
    ],
};
const TEST_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "TestCommandRequest",
    doc: "CLI inputs for one test command invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("json_output_path", FieldDefault::None),
        FieldSpec::new("concurrency", FieldDefault::None),
        FieldSpec::new("case_name", FieldDefault::None),
        FieldSpec::new("inspect", FieldDefault::False),
    ],
};
const REFACTOR_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "RefactorCommandRequest",
    doc: "CLI inputs for one `sqb rename` or `sqb mv` invocation.",
    fields: &[
        FieldSpec::required("command"),
        FieldSpec::required("target"),
        FieldSpec::new("new_name", FieldDefault::None),
        FieldSpec::new("destination", FieldDefault::None),
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("cascade", FieldDefault::False),
        FieldSpec::new("dry_run", FieldDefault::False),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
    ],
};
const SCOPE_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "ScopeCommandRequest",
    doc: "CLI inputs for one offline declaration-scope inspection.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("target", FieldDefault::None),
        FieldSpec::new("at", FieldDefault::None),
        FieldSpec::new("as_path", FieldDefault::None),
        FieldSpec::new("browse", FieldDefault::None),
        FieldSpec::new("list_path", FieldDefault::None),
        FieldSpec::new("defined_under", FieldDefault::None),
        FieldSpec::new("kinds", FieldDefault::EmptyTuple),
        FieldSpec::new("match", FieldDefault::None),
        FieldSpec::new("used_only", FieldDefault::False),
        FieldSpec::new("include_nearby", FieldDefault::False),
        FieldSpec::new("nearby_depth", FieldDefault::Int(1)),
        FieldSpec::new("dependency_depth", FieldDefault::Int(0)),
        FieldSpec::new("explain", FieldDefault::None),
        FieldSpec::new("globals", FieldDefault::Text("summary")),
        FieldSpec::new("page_size", FieldDefault::Int(100)),
        FieldSpec::new("after", FieldDefault::None),
        FieldSpec::new("paths", FieldDefault::Text("relative")),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec::new("verbose", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
    ],
};
const TEST_INVOCATION: RecordSpec = RecordSpec {
    name: "TestInvocation",
    doc: "Resolved project, adapter, and reporter context for the test command.",
    fields: &[
        FieldSpec::required("effective_project_dir"),
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("use_color"),
        FieldSpec::required("progress_stream"),
        FieldSpec::required("connection_progress"),
        FieldSpec::required("planning_progress"),
    ],
};
const RULES_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "RulesCommandRequest",
    doc: "Inputs for focused rule execution, inspection, or skill generation.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("json_output"),
        FieldSpec::required("action"),
        FieldSpec::required("rule_selector"),
        FieldSpec::required("skills_check"),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
    ],
};
const COST_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "CostCommandRequest",
    doc: "Inputs for local run-cost history and drill-down.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("selector"),
        FieldSpec::required("no_color"),
        FieldSpec::required("limit"),
        FieldSpec::required("no_limit"),
        FieldSpec::required("sort"),
        FieldSpec::required("order"),
        FieldSpec::required("since"),
        FieldSpec::required("until"),
        FieldSpec::required("json_output"),
        FieldSpec::required("json_output_path"),
    ],
};
const BUILD_COST_FINALIZATION: RecordSpec = RecordSpec {
    name: "BuildCostFinalization",
    doc: "Inputs for nonfatal automatic build-cost finalization.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::required("adapter_name"),
        FieldSpec::required("adapter"),
        FieldSpec::required("connection_config"),
        FieldSpec::required("target_name"),
        FieldSpec::required("target_database"),
        FieldSpec::required("run_id"),
        FieldSpec::required("build_status"),
        FieldSpec::required("started_at"),
        FieldSpec::required("completed_at"),
        FieldSpec::required("config"),
        FieldSpec::required("output_stream"),
        FieldSpec::required("use_color"),
        FieldSpec::new("collect", FieldDefault::True),
        FieldSpec::new("render", FieldDefault::True),
        FieldSpec::new(
            "cost_status",
            FieldDefault::Member("sqlbuild.cost.types", "CostStatus", "COMPLETE"),
        ),
        FieldSpec::new(
            "cost_message",
            FieldDefault::Text("No executable warehouse work was planned for this build."),
        ),
        FieldSpec::new("had_executable_work", FieldDefault::True),
    ],
};
const CONTRACT_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "ContractCommandRequest",
    doc: "CLI inputs for physical contract comparison and repository adoption.",
    fields: &[
        FieldSpec::required("action"),
        FieldSpec::required("from_target"),
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("write", FieldDefault::False),
        FieldSpec::new("overwrite", FieldDefault::False),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
    ],
};
const LINEAGE_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "LineageCommandRequest",
    doc: "CLI inputs for dependency and column lineage inspection.",
    fields: &[
        FieldSpec::required("project_dir"),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("targets", FieldDefault::EmptyTuple),
        FieldSpec::new("output_format", FieldDefault::Text("tree")),
        FieldSpec::new("direction", FieldDefault::None),
        FieldSpec::new("depth", FieldDefault::Text("all")),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new(
            "lineage_mode",
            FieldDefault::Member(
                "sqlbuild.compiler.lineage.types",
                "ColumnLineageMode",
                "RICH",
            ),
        ),
        FieldSpec::new("include_uses", FieldDefault::False),
        FieldSpec::new("cli_vars", FieldDefault::None),
    ],
};

/// `sqb` command requests and their resolved invocation contexts.
const COMMAND_RECORDS: &[RecordSpec] = &[
    NESTED_PROGRESS_CHILD_ROW,
    AUDIT_COMMAND_REQUEST,
    AUDIT_INVOCATION,
    BUILD_COMMAND_REQUEST,
    BUILD_INVOCATION,
    CHECK_COMMAND_REQUEST,
    CHECK_INVOCATION,
    CLONE_COMMAND_REQUEST,
    DBT_SQLBUILD_WORK_CONTEXT,
    PLAN_SAFETY_GATES,
    DBT_INIT_COMMAND_REQUEST,
    DIFF_COMMAND_REQUEST,
    QUERY_DIFF_PREPARATION,
    FRESHNESS_COMMAND_REQUEST,
    JANITOR_COMMAND_REQUEST,
    JANITOR_INVOCATION,
    JANITOR_SETTINGS,
    LOAD_COMMAND_REQUEST,
    PLAN_COMMAND_REQUEST,
    PLAYGROUND_COMMAND_REQUEST,
    ADAPTER_CONNECTION_CONTEXT,
    SCENARIO_SNAPSHOT_LIMIT_INPUTS,
    SCENARIO_TEST_COMMAND_REQUEST,
    SCENARIO_CAPTURE_COMMAND_REQUEST,
    SEED_COMMAND_REQUEST,
    SEED_INVOCATION,
    TEST_COMMAND_REQUEST,
    REFACTOR_COMMAND_REQUEST,
    SCOPE_COMMAND_REQUEST,
    TEST_INVOCATION,
    RULES_COMMAND_REQUEST,
    COST_COMMAND_REQUEST,
    BUILD_COST_FINALIZATION,
    CONTRACT_COMMAND_REQUEST,
    LINEAGE_COMMAND_REQUEST,
];

const COMPILE_PROFILE_FLAGS: RecordSpec = RecordSpec {
    name: "CompileProfileFlags",
    doc: "Profiling toggles that skip compile phases for benchmarking.",
    fields: &[
        FieldSpec::new("skip_discovery_sql_analysis", FieldDefault::False),
        FieldSpec::new("skip_column_inference", FieldDefault::False),
        FieldSpec::new("skip_contracts", FieldDefault::False),
        FieldSpec::new("skip_write", FieldDefault::False),
    ],
};
const COMPILE_COMMAND_REQUEST: RecordSpec = RecordSpec {
    name: "CompileCommandRequest",
    doc: "CLI inputs for one `sqb compile` invocation.",
    fields: &[
        FieldSpec::new("project_dir", FieldDefault::None),
        FieldSpec::new("no_sql_validation", FieldDefault::False),
        FieldSpec::new("defer_to", FieldDefault::None),
        FieldSpec::new("selected_target", FieldDefault::None),
        FieldSpec::new("json_output", FieldDefault::False),
        FieldSpec::new("manifest", FieldDefault::False),
        FieldSpec::new("dag_path", FieldDefault::None),
        FieldSpec::new("no_color", FieldDefault::False),
        FieldSpec::new(
            "lineage_mode",
            FieldDefault::Member("sqlbuild.cli.commands.types", "CompileLineageMode", "FAST"),
        ),
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("cli_vars", FieldDefault::None),
        FieldSpec::new(
            "profile_flags",
            FieldDefault::Call("sqlbuild._native", "CompileProfileFlags"),
        ),
        FieldSpec::new("no_cache", FieldDefault::False),
        FieldSpec::new("debug", FieldDefault::False),
    ],
};
const SELECTOR_FILE_SUMMARY: RecordSpec = RecordSpec {
    name: "SelectorFileSummary",
    doc: "Non-expanded provenance for one selector file.",
    fields: &[
        FieldSpec::required("path"),
        FieldSpec::required("selector_count"),
    ],
};
const PARSED_CLI_INVOCATION: RecordSpec = RecordSpec {
    name: "ParsedCliInvocation",
    doc: "Outcome of parsing CLI arguments: either a namespace or an exit code.",
    fields: &[
        FieldSpec::required("args"),
        FieldSpec::required("exit_code"),
    ],
};
const CLI_ENTRYPOINT_HANDLERS: RecordSpec = RecordSpec {
    name: "CliEntrypointHandlers",
    doc: "Injected command handlers for the CLI entrypoint.",
    fields: &[
        FieldSpec::required("run_compile"),
        FieldSpec::required("run_cost"),
        FieldSpec::required("run_dag"),
        FieldSpec::required("run_plan"),
        FieldSpec::required("run_dbt_plan"),
        FieldSpec::required("run_dbt_run"),
        FieldSpec::required("run_dbt_build"),
        FieldSpec::required("run_dbt_debug"),
        FieldSpec::required("run_dbt_init"),
        FieldSpec::required("run_build"),
        FieldSpec::required("run_freshness"),
        FieldSpec::required("run_test"),
        FieldSpec::required("run_check"),
        FieldSpec::required("run_audit"),
        FieldSpec::required("run_seed"),
        FieldSpec::required("run_load"),
        FieldSpec::required("run_clone"),
        FieldSpec::required("run_diff"),
        FieldSpec::required("run_query"),
        FieldSpec::required("run_debug"),
        FieldSpec::required("run_lineage"),
        FieldSpec::required("run_janitor"),
        FieldSpec::required("run_init"),
        FieldSpec::required("run_playground"),
        FieldSpec::required("run_skills_update"),
        FieldSpec::required("run_format"),
        FieldSpec::required("run_scenario"),
        FieldSpec::required("run_scenario_capture"),
        FieldSpec::required("run_rules"),
        FieldSpec::required("run_scope"),
        FieldSpec::new("run_contract", FieldDefault::None),
        FieldSpec::new("run_refactor", FieldDefault::None),
    ],
};
const COMMAND_WAREHOUSE_SCOPE: RecordSpec = RecordSpec {
    name: "CommandWarehouseScope",
    doc: "The warehouse group and CLI override active for one command invocation.",
    fields: &[
        FieldSpec::required("group"),
        FieldSpec::new("cli_warehouse", FieldDefault::None),
        FieldSpec::new("cli_vars", FieldDefault::EmptyDict),
    ],
};
const RESOLVED_WAREHOUSE: RecordSpec = RecordSpec {
    name: "ResolvedWarehouse",
    doc: "The warehouse one command connects with and where that value came from.",
    fields: &[
        FieldSpec::required("warehouse"),
        FieldSpec::required("source"),
    ],
};

/// Parsed `sqb` invocations, compile requests, entry handlers and command warehouses.
const ENTRY_RECORDS: &[RecordSpec] = &[
    COMPILE_PROFILE_FLAGS,
    COMPILE_COMMAND_REQUEST,
    SELECTOR_FILE_SUMMARY,
    PARSED_CLI_INVOCATION,
    CLI_ENTRYPOINT_HANDLERS,
    COMMAND_WAREHOUSE_SCOPE,
    RESOLVED_WAREHOUSE,
];

const WRITTEN_TARGET: RecordSpec = RecordSpec {
    name: "WrittenTarget",
    doc: "Result of writing compiled output to target/.",
    fields: &[
        FieldSpec::required("model_count"),
        FieldSpec::required("seed_count"),
        FieldSpec::required("function_count"),
        FieldSpec::required("audit_count"),
        FieldSpec::required("test_count"),
        FieldSpec::required("target_dir"),
        FieldSpec::new("diagnostics", FieldDefault::EmptyTuple),
    ],
};
const SKILL_MAINTENANCE_RESULT: RecordSpec = RecordSpec {
    name: "SkillMaintenanceResult",
    doc: "Non-blocking generated-skill maintenance result.",
    fields: &[FieldSpec::new("message", FieldDefault::Text(""))],
};
const SKILL_UPDATE_RESULT: RecordSpec = RecordSpec {
    name: "SkillUpdateResult",
    doc: "Result of installing or updating skill files.",
    fields: &[FieldSpec::required("written_paths")],
};

/// Compile output and skill maintenance results.
const OUTPUT_RECORDS: &[RecordSpec] = &[
    WRITTEN_TARGET,
    SKILL_MAINTENANCE_RESULT,
    SKILL_UPDATE_RESULT,
];

const COMPILE_ANALYSIS: RecordSpec = RecordSpec {
    name: "CompileAnalysis",
    doc: "Compiled project analysis shared by compile output phases.",
    fields: &[
        FieldSpec::required("discovered_inputs"),
        FieldSpec::required("adapter"),
        FieldSpec::required("graph"),
        FieldSpec::required("selected_keys"),
        FieldSpec::required("lineage"),
        FieldSpec::required("diagnostics"),
        FieldSpec::required("discover_ms"),
        FieldSpec::required("graph_ms"),
        FieldSpec::required("lineage_ms"),
        FieldSpec::required("contract_ms"),
        FieldSpec::required("contract_cpu_ms"),
        FieldSpec::new("built_in_rules_ms", FieldDefault::Int(0)),
        FieldSpec::new("custom_rules_ms", FieldDefault::Int(0)),
        FieldSpec::new("custom_rules_cpu_ms", FieldDefault::Int(0)),
        FieldSpec::new("early_lint_wait_ms", FieldDefault::Int(0)),
        FieldSpec::new("rule_cache_hits", FieldDefault::Int(0)),
        FieldSpec::new("rule_cache_misses", FieldDefault::Int(0)),
        FieldSpec::new("skipped_type_proof_rules", FieldDefault::EmptyTuple),
    ],
};

/// The compiled project analysis shared by compile output phases.
const COMPILE_RECORDS: &[RecordSpec] = &[COMPILE_ANALYSIS];
