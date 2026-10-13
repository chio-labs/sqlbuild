//! Plain facts of one diff result and the options that render it.

use sqlbuild_core::json::models::JsonValue;

use crate::diff_report::types::{DiffNamedValue, DiffTypeChange};

/// One fetched warehouse value: its Python `str()` text and its JSON document form.
#[derive(Clone, Debug, PartialEq)]
pub struct DiffValue {
    pub text: String,
    pub json: JsonValue,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffColumnFacts {
    pub name: String,
    pub mismatched_count: i64,
    /// `str()` of the absolute and relative tolerance, when one is configured.
    pub tolerance: Option<(Option<String>, Option<String>)>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffCoverageFacts {
    pub row_count: i64,
    pub minimum_cursor: Option<DiffValue>,
    pub maximum_cursor: Option<DiffValue>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffRowFacts {
    pub left_count: i64,
    pub right_count: i64,
    pub joined_count: i64,
    pub equal_count: i64,
    pub unequal_count: i64,
    pub left_only_count: i64,
    pub right_only_count: i64,
    pub columns: Vec<DiffColumnFacts>,
    pub population_count: i64,
    pub compared_count: i64,
    /// The configured sample row limit and seed.
    pub sampling: Option<(i64, i64)>,
    pub left_coverage: Option<DiffCoverageFacts>,
    pub right_coverage: Option<DiffCoverageFacts>,
    pub cursor_column: Option<String>,
    pub cursor_start: Option<DiffValue>,
    pub cursor_end: Option<DiffValue>,
    pub exhaustive: bool,
    /// Whether both sides report different cursor extents, by Python value equality.
    pub coverage_differs: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub struct DiffChangedCell {
    pub name: String,
    pub left: DiffValue,
    pub right: DiffValue,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffSampleRow {
    pub key_values: Vec<DiffNamedValue>,
    pub changed_cells: Vec<DiffChangedCell>,
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffModelFacts {
    pub name: String,
    pub left_relation: String,
    pub right_relation: String,
    pub added_columns: Vec<String>,
    pub removed_columns: Vec<String>,
    pub type_changes: Vec<DiffTypeChange>,
    pub unique_key: Vec<String>,
    pub rows: Option<DiffRowFacts>,
    pub unequal_samples: Vec<DiffSampleRow>,
    pub left_only_keys: Vec<Vec<DiffNamedValue>>,
    pub right_only_keys: Vec<Vec<DiffNamedValue>>,
    pub bounded_fallback: bool,
    pub excluded_columns: Vec<String>,
    pub input_kind: String,
    pub unkeyed: bool,
}

/// How example values render: an optional per-value length bound, or suppressed entirely.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct DiffExampleOptions {
    pub max_value_length: Option<usize>,
    pub suppress_values: bool,
}

/// Everything a rendered diff document shows besides the per-model facts.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffDocumentOptions {
    pub from_label: String,
    pub to_label: String,
    pub examples: DiffExampleOptions,
    /// An explicit outcome, such as `incomplete`; otherwise derived from the findings.
    pub outcome: Option<String>,
    /// Per-phase durations of a query diff, in seconds.
    pub phase_seconds: Option<Vec<(String, f64)>>,
}

/// The terminal summary's presentation options.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DiffTextOptions {
    pub mode_label: String,
    pub use_color: bool,
    pub verbose: bool,
    pub max_column_examples: usize,
    pub max_row_only_examples: usize,
}

/// A failed or incomplete diff reported as JSON.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DiffErrorFacts {
    pub status: String,
    pub code: String,
    pub message: String,
    pub help: Option<String>,
    pub size_guard: Option<JsonValue>,
}

/// One value rendered for display: bounded around the first difference, or suppressed.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct RenderedValue {
    pub(crate) text: Option<String>,
    pub(crate) original_length: usize,
    pub(crate) truncated: bool,
    pub(crate) suppressed: bool,
    pub(crate) first_difference: Option<usize>,
}
