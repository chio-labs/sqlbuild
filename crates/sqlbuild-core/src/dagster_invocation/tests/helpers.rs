//! Shared builders for Dagster invocation tests.

use crate::dagster_invocation::models::FailedCheck;

/// Owned copies of string literals.
pub(super) fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}

/// A failed `not_null` audit on `model.order_id`.
pub(super) fn not_null_audit(model: &str, row_count: Option<i64>) -> FailedCheck {
    FailedCheck {
        kind: "audit".to_owned(),
        name: "not_null".to_owned(),
        asset_name: Some(model.to_owned()),
        column_name: Some("order_id".to_owned()),
        status: "error".to_owned(),
        row_count,
    }
}
