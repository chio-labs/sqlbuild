//! The line comment prefixes a dialect declares that SQLBuild cannot scan.

use crate::sql_scan::constants::SUPPORTED_LINE_COMMENT_PREFIXES;

/// The declared prefixes outside the supported set, sorted and without repeats.
#[must_use]
pub fn unsupported_line_comment_prefixes(prefixes: &[String]) -> Vec<String> {
    let mut unsupported: Vec<String> = prefixes
        .iter()
        .filter(|prefix| !SUPPORTED_LINE_COMMENT_PREFIXES.contains(&prefix.as_str()))
        .cloned()
        .collect();
    unsupported.sort_unstable();
    unsupported.dedup();
    unsupported
}
