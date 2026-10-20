//! Python's literal spellings of the plain config values.

pub(crate) const NONE_TEXT: &str = "None";
pub(crate) const TRUE_TEXT: &str = "True";
pub(crate) const FALSE_TEXT: &str = "False";
pub(crate) const TAGS_KEY: &str = "tags";
pub(crate) const ROW_DIFF_EXCLUDE_COLUMNS_KEY: &str = "row_diff_exclude_columns";
pub(crate) const ROW_DIFF_TOLERANCES_KEY: &str = "row_diff_tolerances";
/// The `row_diff_tolerances` sections merged one level deeper than the rest.
pub(crate) const AUDIT_OVERRIDE_SECTIONS: [&str; 2] = ["by_type", "by_column"];
pub(crate) const EXPECTED_TEXT: &str = "a string";
pub(crate) const EXPECTED_FLAG: &str = "a boolean";
pub(crate) const EXPECTED_TEXTS: &str = "a list or tuple of strings";
pub(crate) const EXPECTED_INTEGER: &str = "an integer";
pub(crate) const EXPECTED_CURSOR_BOUND: &str = "a string, integer, date, or datetime";
