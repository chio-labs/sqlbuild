//! Native behaviour of the hosted shapes: computed attributes, methods, ordering and validation.

use crate::bindings::_helpers::record_behaviours::auditing::{
    finish_measurement_contract, finish_threshold_bound, finish_thresholds,
};
use crate::bindings::_helpers::record_behaviours::config::settings_sql_validation;
use crate::bindings::_helpers::record_behaviours::durations::{
    duration_add_to, duration_fixed_seconds, duration_has_calendar_component,
    duration_is_single_unit_in, duration_is_zero, duration_parse, duration_subtract_from,
    duration_total_months, duration_units, finish_aligned_interval,
};
use crate::bindings::_helpers::record_behaviours::freshness::{
    finish_freshness_record, freshness_record_identity,
};
use crate::bindings::_helpers::record_behaviours::lexical::{
    finish_lexical_syntax, lexical_cache_key, lexical_native_mapping, lexical_reads_differently,
};
use crate::bindings::_helpers::record_behaviours::python_nodes::graph_selected_sql_refs;
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
];
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
    ("Duration", "subtract_from", duration_subtract_from),
];
/// Compiler records ordered by their compared fields.
pub(crate) const BEHAVIOUR_ORDERED: &[&str] =
    &["ResourceIdentity", "DeclarationIdentity", "OwnershipRoot"];
