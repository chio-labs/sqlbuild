//! Authoritative schema requirements for empty fixtures.

use crate::planner_fixtures::models::FixtureColumn;

/// Return the first schema failure before rendering any empty-fixture column.
pub fn empty_fixture_error(authoritative: bool, columns: &[FixtureColumn]) -> Option<String> {
    if !authoritative {
        return Some("uses __empty_fixture() but its column schema is not authoritative".into());
    }
    let unknown: Vec<_> = columns
        .iter()
        .filter(|column| column.sql_type.is_none())
        .map(|column| column.name.as_str())
        .collect();
    if !unknown.is_empty() {
        return Some(format!(
            "uses __empty_fixture() but columns have unknown types: {}",
            unknown.join(", ")
        ));
    }
    if columns.is_empty() {
        return Some("uses __empty_fixture() but its schema has no columns".into());
    }
    None
}
