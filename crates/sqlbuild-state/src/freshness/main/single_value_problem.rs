//! `single_value_problem`: why a freshness query result is not one non-null value.

use crate::freshness::models::QueryShape;

/// The observation error message for a result that is not exactly one non-null value.
pub fn single_value_problem(source_name: &str, shape: QueryShape) -> Option<String> {
    if shape.columns != 1 {
        return Some(format!(
            "source '{source_name}' freshness query must return exactly one column"
        ));
    }
    if shape.rows != 1 {
        return Some(format!(
            "source '{source_name}' freshness query must return exactly one row"
        ));
    }
    shape
        .first_value_null
        .then(|| format!("source '{source_name}' freshness data_version cannot be null"))
}
