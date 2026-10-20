//! `fill_finding_path`: a SQL finding's help with its file's path written into the entry it prints.

use crate::sql_lint::constants::CROSS_JOIN_PATH_PLACEHOLDER;

/// `remediation` with the path placeholder of a printed exception entry replaced by `path`.
#[must_use]
pub fn fill_finding_path(remediation: &str, path: &str) -> String {
    remediation.replace(CROSS_JOIN_PATH_PLACEHOLDER, path)
}
