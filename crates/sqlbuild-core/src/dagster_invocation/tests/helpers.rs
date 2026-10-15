//! Shared builders for Dagster invocation tests.

/// Owned copies of string literals.
pub(super) fn owned(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| (*value).to_owned()).collect()
}
