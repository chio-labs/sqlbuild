//! Legacy fixture star-analysis marker substitution.

use crate::planner_fixtures::constants::MARKER_PATTERNS;
use regex::Regex;
use std::sync::LazyLock;

static MARKERS: LazyLock<Result<Vec<Regex>, regex::Error>> =
    LazyLock::new(|| MARKER_PATTERNS.into_iter().map(Regex::new).collect());

/// Substitute exact marker forms, including matches in SQL comments and strings.
pub(crate) fn stub_markers(sql: &str) -> Result<String, regex::Error> {
    Ok(MARKERS
        .as_ref()
        .map_err(Clone::clone)?
        .iter()
        .fold(sql.to_owned(), |sql, pattern| {
            pattern.replace_all(&sql, "$1").into_owned()
        }))
}
