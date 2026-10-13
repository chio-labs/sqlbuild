//! Fixed widths and limits of the diff summary.

pub(crate) const SUMMARY_WIDTH: usize = 110;
pub(crate) const TOP_CHANGED_COLUMNS: usize = 5;
pub(crate) const MAX_RENDERED_KEY_LENGTH: usize = 256;
pub(crate) const CHANGED_COLUMN_NAME_WIDTH: usize = 32;
pub(crate) const QUERY_INPUT_KIND: &str = "query";
pub(crate) const FINDINGS_OUTCOME: &str = "findings";
pub(crate) const PASS_OUTCOME: &str = "pass";
pub(crate) const INCOMPLETE_OUTCOME: &str = "incomplete";
pub(crate) const BOUNDED_WINDOW_PLACEHOLDER: &str = "<window>";
/// Root expression kinds a raw diff query may have.
pub(crate) const READ_ONLY_QUERY_ROOT_KEYS: [&str; 5] =
    ["except", "intersect", "select", "union", "values"];
/// Expression kinds that make a raw diff query change data or state.
pub(crate) const MUTATING_QUERY_KEYS: [&str; 19] = [
    "alter",
    "command",
    "copy",
    "create",
    "delete",
    "drop",
    "execute",
    "grant",
    "insert",
    "load_data",
    "merge",
    "pragma",
    "revoke",
    "set",
    "transaction",
    "truncate",
    "uncache",
    "update",
    "use",
];
pub(crate) const INCOMPLETE_PREPARATION_CODES: [&str; 9] = [
    "C229", "C230", "C231", "C232", "C233", "C234", "C235", "C240", "C244",
];
pub(crate) const INCOMPLETE_EXECUTION_CODES: [&str; 3] = ["C237", "C238", "C239"];
pub(crate) const DEFAULT_EXAMPLES: i64 = 3;
pub(crate) const VERBOSE_EXAMPLES: i64 = 10;
