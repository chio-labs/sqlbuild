//! The query comparing a scenario's actual output with its expected SQL.

/// Actual, expected and mismatched row counts of one scenario expectation.
#[must_use]
pub fn scenario_expected_comparison_sql(
    actual_sql: &str,
    expected_sql: &str,
    set_difference_operator: &str,
) -> String {
    format!(
        "WITH __actual AS ({actual_sql}), __expected AS ({expected_sql}) SELECT \
         (SELECT COUNT(*) FROM __actual) AS actual_count, \
         (SELECT COUNT(*) FROM __expected) AS expected_count, \
         (SELECT COUNT(*) FROM (SELECT * FROM __actual {set_difference_operator} SELECT * FROM __expected\
         ) AS __sqlbuild_mismatch) AS mismatched_count"
    )
}
