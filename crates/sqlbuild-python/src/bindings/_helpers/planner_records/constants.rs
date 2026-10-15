//! Layouts of the planner, migration, cursor and fingerprint value records hosted natively.

use crate::bindings::_helpers::records::models::{FieldDefault, FieldSpec, RecordSpec};

const R_PARSED_SELECTOR: RecordSpec = RecordSpec {
    name: "ParsedSelector",
    doc: "One parsed selector token before graph resolution.",
    fields: &[
        FieldSpec::required("kind"),
        FieldSpec::required("value"),
        FieldSpec::new("upstream", FieldDefault::False),
        FieldSpec::new("downstream", FieldDefault::False),
    ],
};
const R_PATH_SELECTOR: RecordSpec = RecordSpec {
    name: "PathSelector",
    doc: "A directed path selector between two model names with optional endpoint expansion.",
    fields: &[
        FieldSpec::required("start_name"),
        FieldSpec::required("end_name"),
        FieldSpec::new("upstream", FieldDefault::False),
        FieldSpec::new("downstream", FieldDefault::False),
    ],
};
const R_SQL_TEST_SELECTION: RecordSpec = RecordSpec {
    name: "SqlTestSelection",
    doc: "Unit tests selected or excluded by name, beside the tests of the selected resources.",
    fields: &[
        FieldSpec::new("names", FieldDefault::EmptyFrozenset),
        FieldSpec::new("excluded_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new("models_selected", FieldDefault::True),
    ],
};
const R_PLANNER_SCOPE: RecordSpec = RecordSpec {
    name: "PlannerScope",
    doc: "Resolved graph scope for one planner invocation.",
    fields: &[
        FieldSpec::required("upstream_deps"),
        FieldSpec::required("downstream_deps"),
        FieldSpec::required("all_keys"),
        FieldSpec::required("models_by_name"),
        FieldSpec::required("selected_keys"),
        FieldSpec::required("execution_order"),
        FieldSpec::new("user_selected_keys", FieldDefault::EmptyFrozenset),
        FieldSpec::new("python_read_source_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new(
            "sql_test_selection",
            FieldDefault::Call("sqlbuild._native", "SqlTestSelection"),
        ),
    ],
};
const R_PLANNER_RELATIONS_CONTEXT: RecordSpec = RecordSpec {
    name: "PlannerRelationsContext",
    doc: "Resolved relation and source inputs for plan entry construction.",
    fields: &[
        FieldSpec::required("model_locations"),
        FieldSpec::required("seed_locations"),
        FieldSpec::required("function_locations"),
        FieldSpec::required("source_map"),
        FieldSpec::required("source_read_map"),
        FieldSpec::required("python_source_read_map"),
        FieldSpec::required("source_warehouse_columns"),
        FieldSpec::required("star_exclude_keyword"),
        FieldSpec::new("listed_source_names", FieldDefault::EmptyFrozenset),
    ],
};
const R_SQL_TEST_ASSERTION_STEP: RecordSpec = RecordSpec {
    name: "SqlTestAssertionStep",
    doc: "One zero-row assertion step in a SQL-native unit test.",
    fields: &[
        FieldSpec::required("name"),
        FieldSpec::required("resolved_sql"),
        FieldSpec::new("lifted_ctes", FieldDefault::EmptyTuple),
        FieldSpec::new("comparison_body_sql", FieldDefault::None),
    ],
};
const R_PLANNER_SELECTION: RecordSpec = RecordSpec {
    name: "PlannerSelection",
    doc: "User-facing selection inputs for one planner invocation.",
    fields: &[
        FieldSpec::new("select", FieldDefault::EmptyTuple),
        FieldSpec::new("exclude", FieldDefault::EmptyTuple),
        FieldSpec::new("selected_keys", FieldDefault::None),
        FieldSpec::new("python_read_source_names", FieldDefault::EmptyFrozenset),
        FieldSpec::new(
            "sql_test_selection",
            FieldDefault::Call("sqlbuild._native", "SqlTestSelection"),
        ),
    ],
};
const R_PLANNER_OVERRIDES: RecordSpec = RecordSpec {
    name: "PlannerOverrides",
    doc: "Explicit user overrides that force or bound planner decisions.",
    fields: &[
        FieldSpec::new("cursor_overrides", FieldDefault::None),
        FieldSpec::new("full_refresh", FieldDefault::False),
        FieldSpec::new("reload_sources", FieldDefault::False),
        FieldSpec::new("forced_stale_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("external_blocked_model_names", FieldDefault::EmptyTuple),
        FieldSpec::new("max_microbatches", FieldDefault::None),
    ],
};
const R_DEFERRAL_INPUTS: RecordSpec = RecordSpec {
    name: "DeferralInputs",
    doc: "Deferred relation and source-deferral inputs for planning.",
    fields: &[
        FieldSpec::new("deferred_locations", FieldDefault::None),
        FieldSpec::new("deferred_relations", FieldDefault::None),
        FieldSpec::new("defer_sources_to", FieldDefault::None),
        FieldSpec::new("source_deferral_enabled", FieldDefault::True),
    ],
};
const R_PLANNER_POLICIES: RecordSpec = RecordSpec {
    name: "PlannerPolicies",
    doc: "Behavior policies selected by the caller for one planner invocation.",
    fields: &[
        FieldSpec::new("auto_load_sources", FieldDefault::False),
        FieldSpec::new("selection_diagnostics", FieldDefault::False),
        FieldSpec::new("plan_sql_tests", FieldDefault::True),
        FieldSpec::new("record_migration_fingerprints", FieldDefault::True),
    ],
};
const R_DIRECT_SOURCE_FRESHNESS_PLANNING_RESULT: RecordSpec = RecordSpec {
    name: "DirectSourceFreshnessPlanningResult",
    doc: "Direct planning-time source freshness observations and comparisons.",
    fields: &[
        FieldSpec::new("observed_records", FieldDefault::EmptyTuple),
        FieldSpec::new("previous_records", FieldDefault::EmptyTuple),
        FieldSpec::new("changed_identities", FieldDefault::EmptyFrozenset),
        FieldSpec::new("unchanged_identities", FieldDefault::EmptyFrozenset),
        FieldSpec::new("unknown_source_names", FieldDefault::EmptyTuple),
        FieldSpec::new("unknown_sources", FieldDefault::EmptyDict),
        FieldSpec::new("age_statuses", FieldDefault::EmptyDict),
        FieldSpec::new("propagation", FieldDefault::None),
    ],
};
const R_FINGERPRINT: RecordSpec = RecordSpec {
    name: "Fingerprint",
    doc: "One applied fingerprint record from a successful materialization.",
    fields: &[
        FieldSpec::required("node_type"),
        FieldSpec::required("node_name"),
        FieldSpec::required("target_database"),
        FieldSpec::required("target_schema"),
        FieldSpec::required("target_name"),
        FieldSpec::required("run_id"),
        FieldSpec::required("definition_hash"),
        FieldSpec::required("schema_fingerprint"),
        FieldSpec::required("definition"),
        FieldSpec::required("ts"),
        FieldSpec::new("metadata_json", FieldDefault::Text("{}")),
        FieldSpec::new("version_hash", FieldDefault::Text("")),
    ],
};
const R_FINGERPRINT_SET: RecordSpec = RecordSpec {
    name: "FingerprintSet",
    doc: "Latest fingerprints per node name for one target schema.",
    fields: &[
        FieldSpec::required("schema"),
        FieldSpec::required("fingerprints"),
        FieldSpec::new("fingerprints_by_identity", FieldDefault::None),
    ],
};
const R_SOURCE_FRESHNESS_RECORD: RecordSpec = RecordSpec {
    name: "SourceFreshnessRecord",
    doc: "One append-only direct observation whose observed time is always aware UTC.",
    fields: &[
        FieldSpec::required("source_name"),
        FieldSpec::required("target_database"),
        FieldSpec::required("target_schema"),
        FieldSpec::required("target_name"),
        FieldSpec::required("run_id"),
        FieldSpec::required("strategy"),
        FieldSpec::required("value_kind"),
        FieldSpec::required("data_version"),
        FieldSpec::required("data_version_hash"),
        FieldSpec::required("observed_at"),
    ],
};
const R_TIMESTAMP_VALUE: RecordSpec = RecordSpec {
    name: "TimestampValue",
    doc: "Timestamp cursor value; aware datetimes are normalized to UTC at ingestion.",
    fields: &[
        FieldSpec::required("value"),
        FieldSpec {
            name: "source_text",
            default: FieldDefault::None,
            compared: false,
        },
    ],
};
const R_DATE_VALUE: RecordSpec = RecordSpec {
    name: "DateValue",
    doc: "Date cursor value which must remain date-formatted when rendered.",
    fields: &[FieldSpec::required("value")],
};
const R_INTEGER_VALUE: RecordSpec = RecordSpec {
    name: "IntegerValue",
    doc: "Integral cursor value.",
    fields: &[FieldSpec::required("value")],
};
const R_ALIGNED_INTERVAL: RecordSpec = RecordSpec {
    name: "AlignedInterval",
    doc: "Validated half-open cursor interval.",
    fields: &[
        FieldSpec::required("start"),
        FieldSpec::required("end"),
        FieldSpec::required("grain"),
    ],
};
const R_DURATION: RecordSpec = RecordSpec {
    name: "Duration",
    doc: "A calendar-aware duration (years/months plus fixed time units).",
    fields: &[
        FieldSpec::new("years", FieldDefault::Int(0)),
        FieldSpec::new("months", FieldDefault::Int(0)),
        FieldSpec::new("days", FieldDefault::Int(0)),
        FieldSpec::new("hours", FieldDefault::Int(0)),
        FieldSpec::new("minutes", FieldDefault::Int(0)),
        FieldSpec::new("seconds", FieldDefault::Int(0)),
    ],
};

/// The planner, migration, cursor and fingerprint value records.
pub(crate) const PLANNER_RECORDS: &[RecordSpec] = &[
    R_PARSED_SELECTOR,
    R_PATH_SELECTOR,
    R_SQL_TEST_SELECTION,
    R_PLANNER_SCOPE,
    R_PLANNER_RELATIONS_CONTEXT,
    R_SQL_TEST_ASSERTION_STEP,
    R_PLANNER_SELECTION,
    R_PLANNER_OVERRIDES,
    R_DEFERRAL_INPUTS,
    R_PLANNER_POLICIES,
    R_DIRECT_SOURCE_FRESHNESS_PLANNING_RESULT,
    R_FINGERPRINT,
    R_FINGERPRINT_SET,
    R_SOURCE_FRESHNESS_RECORD,
    R_TIMESTAMP_VALUE,
    R_DATE_VALUE,
    R_INTEGER_VALUE,
    R_ALIGNED_INTERVAL,
    R_DURATION,
];
