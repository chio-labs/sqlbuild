//! Native behaviour of the hosted shapes: computed attributes, methods, ordering and validation.

use crate::bindings::_helpers::record_behaviours::auditing::{
    finish_measurement_contract, finish_threshold_bound, finish_thresholds,
};
use crate::bindings::_helpers::record_behaviours::config::settings_sql_validation;
use crate::bindings::_helpers::record_behaviours::cursors::{
    finish_cursor_bounds, finish_cursor_snapshot, finish_future_evidence, finish_input_evidence,
    finish_input_relation, finish_maximum_evidence, input_relation_runtime_owned,
    snapshot_watermarks_available,
};
use crate::bindings::_helpers::record_behaviours::discovery::{
    constant_logical_type, constant_scalar_type, graph_all_keys, graph_downstream_deps,
    graph_lineage_views, graph_path_index, graph_tag_index, graph_upstream_deps,
};
use crate::bindings::_helpers::record_behaviours::durations::{
    duration_add_to, duration_fixed_seconds, duration_has_calendar_component,
    duration_is_single_unit_in, duration_is_zero, duration_parse, duration_subtract_from,
    duration_total_months, duration_units, finish_aligned_interval,
};
use crate::bindings::_helpers::record_behaviours::error_inits::{
    macro_argument_error_init, macro_argument_error_located, macro_argument_error_shifted,
    rules_config_error_init, sql_test_reference_error_init,
};
use crate::bindings::_helpers::record_behaviours::freshness::{
    finish_freshness_record, freshness_record_identity,
};
use crate::bindings::_helpers::record_behaviours::lexical::{
    finish_lexical_syntax, lexical_cache_key, lexical_native_mapping, lexical_reads_differently,
};
use crate::bindings::_helpers::record_behaviours::migrations::{
    column_decision_blocks_build, column_decision_label, column_decision_records_event,
    column_decision_renames, column_event_mentions, column_event_renamed, decision_blocks_build,
    decision_checks_compatibility, decision_moves_data, event_mentions, history_new, history_old,
    history_status, relation_identity_property, relation_matches, value_plan_label,
};
use crate::bindings::_helpers::record_behaviours::planner::{
    column_migration_blocks_build, column_migration_origin_missing, finish_cursor_overrides,
    materialization_is_table_backed, model_migration_blocks_build, model_migration_origin_hidden,
    model_migration_origin_missing, model_migration_storage_transition,
    model_migration_target_label, old_name_runs_steps, overrides_have_untyped, overrides_typed_as,
    plan_python_source_entries, retention_decreases,
};
use crate::bindings::_helpers::record_behaviours::python_nodes::graph_selected_sql_refs;
use crate::bindings::_helpers::record_behaviours::references::{
    reference_example_call, reference_fixture_cte_prefix, reference_function_name,
    reference_placeholder_call,
};
use crate::bindings::_helpers::record_behaviours::scopes::{
    completeness_complete, target_query_unknown,
};
use crate::bindings::_helpers::record_behaviours::values::{
    finish_fingerprint_set, logical_type_display_name, sql_value_kind,
};
use crate::bindings::_helpers::records::types::{ClassMethod, ClassProperty, RecordFinish};

/// Compiler records whose bound values are normalized or validated natively.
pub(crate) const BEHAVIOUR_FINISHERS: &[(&str, RecordFinish)] = &[
    ("MeasurementThresholdBound", finish_threshold_bound),
    ("MeasurementThresholds", finish_thresholds),
    ("MeasurementContract", finish_measurement_contract),
    ("FingerprintSet", finish_fingerprint_set),
    ("SourceFreshnessRecord", finish_freshness_record),
    ("SqlLexicalSyntax", finish_lexical_syntax),
    ("AlignedInterval", finish_aligned_interval),
    ("CursorOverrides", finish_cursor_overrides),
    ("ModelCursorSnapshot", finish_cursor_snapshot),
    ("CursorBounds", finish_cursor_bounds),
    ("CursorInputEvidence", finish_input_evidence),
    ("FutureCursorSafetyEvidence", finish_future_evidence),
    ("MaximumStartSafetyEvidence", finish_maximum_evidence),
    ("CursorInputRelation", finish_input_relation),
];
/// Computed attributes of compiler shapes.
pub(crate) const BEHAVIOUR_PROPERTIES: &[(&str, &str, ClassProperty)] = &[
    ("ScopeCompleteness", "complete", completeness_complete),
    ("ScopeTargetQuery", "unknown", target_query_unknown),
    ("SettingsConfig", "sql_validation", settings_sql_validation),
    ("SqlLogicalType", "display_name", logical_type_display_name),
    ("SqlValue", "kind", sql_value_kind),
    (
        "SourceFreshnessRecord",
        "identity",
        freshness_record_identity,
    ),
    ("SqlLexicalSyntax", "cache_key", lexical_cache_key),
    ("SqlLexicalSyntax", "native_mapping", lexical_native_mapping),
    ("Duration", "is_zero", duration_is_zero),
    ("Duration", "units", duration_units),
    (
        "Duration",
        "has_calendar_component",
        duration_has_calendar_component,
    ),
    ("Duration", "fixed_seconds", duration_fixed_seconds),
    ("Duration", "total_months", duration_total_months),
    ("MigrationDecision", "moves_data", decision_moves_data),
    ("MigrationDecision", "blocks_build", decision_blocks_build),
    (
        "MigrationDecision",
        "checks_compatibility",
        decision_checks_compatibility,
    ),
    ("MigrationDecision", "label", value_plan_label),
    ("MigrationPromotion", "label", value_plan_label),
    (
        "ColumnMigrationDecision",
        "renames",
        column_decision_renames,
    ),
    (
        "ColumnMigrationDecision",
        "records_event",
        column_decision_records_event,
    ),
    (
        "ColumnMigrationDecision",
        "blocks_build",
        column_decision_blocks_build,
    ),
    ("ColumnMigrationDecision", "label", column_decision_label),
    ("MigrationRelation", "identity", relation_identity_property),
    ("OldNameViewHistory", "old", history_old),
    ("OldNameViewHistory", "new", history_new),
    ("CursorOverrides", "has_untyped", overrides_have_untyped),
    (
        "ModelCursorSnapshot",
        "watermarks_available",
        snapshot_watermarks_available,
    ),
    (
        "CursorInputRelation",
        "is_runtime_owned",
        input_relation_runtime_owned,
    ),
    ("RetentionPlanEntry", "decreases", retention_decreases),
    (
        "ModelMigrationPlanEntry",
        "origin_missing",
        model_migration_origin_missing,
    ),
    (
        "ModelMigrationPlanEntry",
        "origin_hidden",
        model_migration_origin_hidden,
    ),
    (
        "ModelMigrationPlanEntry",
        "storage_transition",
        model_migration_storage_transition,
    ),
    (
        "ModelMigrationPlanEntry",
        "target_label",
        model_migration_target_label,
    ),
    (
        "ModelMigrationPlanEntry",
        "blocks_build",
        model_migration_blocks_build,
    ),
    ("OldNameViewPlanEntry", "runs_steps", old_name_runs_steps),
    (
        "ColumnMigrationPlanEntry",
        "origin_missing",
        column_migration_origin_missing,
    ),
    (
        "ColumnMigrationPlanEntry",
        "blocks_build",
        column_migration_blocks_build,
    ),
    (
        "PlanOutput",
        "python_source_entries",
        plan_python_source_entries,
    ),
    ("SqlReferenceKind", "function_name", reference_function_name),
    (
        "SqlReferenceKind",
        "fixture_cte_prefix",
        reference_fixture_cte_prefix,
    ),
    ("ConstantDeclaration", "logical_type", constant_logical_type),
    ("ConstantDeclaration", "scalar_type", constant_scalar_type),
    ("ProjectGraph", "upstream_deps", graph_upstream_deps),
    ("ProjectGraph", "downstream_deps", graph_downstream_deps),
    ("ProjectGraph", "tag_index", graph_tag_index),
    ("ProjectGraph", "path_index", graph_path_index),
    ("ProjectGraph", "all_keys", graph_all_keys),
];
/// Computed attributes of compiler shapes that a record computes once and keeps.
pub(crate) const BEHAVIOUR_CACHED_PROPERTIES: &[(&str, &str, ClassProperty)] =
    &[("ProjectGraph", "lineage_views", graph_lineage_views)];
/// Methods of compiler shapes.
pub(crate) const BEHAVIOUR_METHODS: &[(&str, &str, ClassMethod)] = &[
    (
        "SqlLexicalSyntax",
        "reads_differently_from_generic",
        lexical_reads_differently,
    ),
    ("Duration", "parse", duration_parse),
    (
        "PythonNodeGraph",
        "selected_sql_refs",
        graph_selected_sql_refs,
    ),
    ("Duration", "is_single_unit_in", duration_is_single_unit_in),
    ("Duration", "add_to", duration_add_to),
    ("MigrationRelation", "matches", relation_matches),
    ("MigrationEvent", "mentions", event_mentions),
    ("ColumnMigrationEvent", "mentions", column_event_mentions),
    ("ColumnMigrationEvent", "renamed", column_event_renamed),
    ("OldNameViewHistory", "status", history_status),
    (
        "MaterializationType",
        "is_table_backed",
        materialization_is_table_backed,
    ),
    ("CursorOverrides", "typed_as", overrides_typed_as),
    ("SqlReferenceKind", "example_call", reference_example_call),
    (
        "SqlReferenceKind",
        "placeholder_call",
        reference_placeholder_call,
    ),
    ("MacroArgumentError", "__init__", macro_argument_error_init),
    (
        "MacroArgumentError",
        "shifted",
        macro_argument_error_shifted,
    ),
    (
        "MacroArgumentError",
        "located",
        macro_argument_error_located,
    ),
    (
        "SqlTestReferenceError",
        "__init__",
        sql_test_reference_error_init,
    ),
    ("RulesConfigError", "__init__", rules_config_error_init),
    ("Duration", "subtract_from", duration_subtract_from),
];
/// Compiler records ordered by their compared fields.
pub(crate) const BEHAVIOUR_ORDERED: &[&str] =
    &["ResourceIdentity", "DeclarationIdentity", "OwnershipRoot"];
