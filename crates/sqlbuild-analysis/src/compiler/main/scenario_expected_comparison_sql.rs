//! The query comparing a scenario's actual output with its expected SQL.

use crate::compiler::_helpers::sql_tests::rendering::{
    compared_columns_projection, comparison_counts_sql,
};

/// Row counts of one scenario expectation, comparing `compared_columns` by name, else all by position.
#[must_use]
pub fn scenario_expected_comparison_sql(
    actual_sql: &str,
    expected_sql: &str,
    compared_columns: Option<&[String]>,
    set_difference_operator: &str,
) -> String {
    format!(
        "WITH __actual AS ({actual_sql}), __expected AS ({expected_sql}) SELECT {}",
        comparison_counts_sql(
            ("__actual", "__expected"),
            &compared_columns_projection(compared_columns),
            set_difference_operator,
        )
    )
}
