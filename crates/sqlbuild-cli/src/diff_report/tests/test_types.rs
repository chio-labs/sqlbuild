use sqlbuild_core::json::errors::JsonEmitError;

use crate::diff_report::models::{DiffExampleOptions, DiffModelFacts, DiffRequestFacts};

/// Two unequal values, how they render, and what the rendering reports.
pub(crate) struct EvidenceTestCase {
    pub(crate) description: &'static str,
    pub(crate) left: String,
    pub(crate) right: String,
    pub(crate) options: DiffExampleOptions,
    pub(crate) expected_left: String,
    pub(crate) expected_right: String,
    pub(crate) expected_first_difference: Option<usize>,
}

/// Diff results and the outcome and exit code they produce.
pub(crate) struct OutcomeTestCase {
    pub(crate) description: &'static str,
    pub(crate) models: Vec<DiffModelFacts>,
    pub(crate) query_row_comparison: bool,
    pub(crate) expected_outcome: (&'static str, i32),
}

/// One model and fragments its terminal summary must contain.
pub(crate) struct SummaryTestCase {
    pub(crate) description: &'static str,
    pub(crate) model: DiffModelFacts,
    pub(crate) expected_lines: &'static [&'static str],
}

/// A key value and how its rendering starts and ends.
pub(crate) struct KeyTestCase {
    pub(crate) description: &'static str,
    pub(crate) key: String,
    pub(crate) expected_prefix: String,
    pub(crate) expected_suffix: String,
}

/// A rendered JSON document and a fragment it must contain.
pub(crate) struct JsonTestCase {
    pub(crate) description: &'static str,
    pub(crate) document: Result<String, JsonEmitError>,
    pub(crate) expected_fragment: &'static str,
}

/// A positional target range and its parsed targets or error code.
pub(crate) struct NameRangeTestCase {
    pub(crate) description: &'static str,
    pub(crate) range: &'static str,
    pub(crate) expected_targets: Result<(String, Option<String>), String>,
}

/// Request flags and the code of the first rule they violate.
pub(crate) struct RequestTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: DiffRequestFacts,
    pub(crate) expected_code: Option<&'static str>,
}

/// A blocked model's request scope and the guard's replacement commands.
pub(crate) struct SizeGuardTestCase {
    pub(crate) description: &'static str,
    pub(crate) request: DiffRequestFacts,
    pub(crate) has_cursor: bool,
    pub(crate) expected_full: &'static str,
    pub(crate) expected_bounded: Option<&'static str>,
    pub(crate) expected_fragments: &'static [&'static str],
}

/// Query columns, a column limit and the preflight error code.
pub(crate) struct ColumnsTestCase {
    pub(crate) description: &'static str,
    pub(crate) columns: &'static [&'static str],
    pub(crate) max_columns: Option<i64>,
    pub(crate) expected_outcome: Result<(), (&'static str, &'static str)>,
}
