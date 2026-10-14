//! Exact empty-fixture marker recognition.

use crate::planner_fixtures::constants::EMPTY_PATTERN;
use regex::Regex;
use std::sync::OnceLock;

/// Whether SQL consists solely of the empty-fixture marker.
pub fn empty_fixture_marker(sql: &str) -> Result<bool, regex::Error> {
    static PATTERN: OnceLock<Result<Regex, regex::Error>> = OnceLock::new();
    PATTERN
        .get_or_init(|| Regex::new(EMPTY_PATTERN))
        .as_ref()
        .map(|pattern| pattern.is_match(sql))
        .map_err(Clone::clone)
}
