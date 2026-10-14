//! Contract-aware fixture projection formatting.

/// Remove typed nulls only when fixture completion restores the authored schema order.
pub fn simplify_fixture_nulls(
    sql: &str,
    columns: &[(String, Option<String>, Option<bool>)],
) -> Result<String, regex::Error> {
    crate::lint_text::_helpers::fixture_formatting::simplify_fixture_nulls(sql, columns)
}
