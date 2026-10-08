use crate::model_validation::models::ProjectValidationFacts;
use crate::tests::test_types::Value;

/// A list of strings.
pub(super) fn strings(values: &[&str]) -> Value {
    Value::List(values.iter().map(|value| Value::Str(leak(value))).collect())
}

/// A string that lives for the whole test run.
fn leak(value: &str) -> &'static str {
    Box::leak(value.to_owned().into_boxed_str())
}

/// A mapping from string keys.
pub(super) fn map(entries: Vec<(&'static str, Value)>) -> Value {
    Value::Map(
        entries
            .into_iter()
            .map(|(key, value)| (Value::Str(key), value))
            .collect(),
    )
}

/// The project's resources and custom materializations.
pub(super) fn project() -> ProjectValidationFacts {
    let names = |values: &[&str]| values.iter().map(|value| (*value).to_owned()).collect();
    ProjectValidationFacts {
        custom_materializations: names(&["ledger"]),
        microbatch_concurrency: false,
        models: names(&["orders", "customers"]),
        seeds: names(&["regions"]),
        sources: names(&["raw.orders"]),
        functions: names(&["cents", "order_lines"]),
        table_functions: names(&["order_lines"]),
    }
}

/// An append incremental config with a daily timestamp cursor, plus `extra`.
pub(super) fn incremental(extra: Vec<(&'static str, Value)>) -> Vec<(&'static str, Value)> {
    let mut config = vec![
        ("materialized", Value::Str("incremental")),
        ("incremental_strategy", Value::Str("append")),
        ("cursor", Value::Str("updated_at")),
        ("cursor_type", Value::Str("timestamp")),
        ("cursor_grain", Value::Str("day")),
    ];
    config.extend(extra);
    config
}

/// A timestamp snapshot config, plus `extra`.
pub(super) fn snapshot(extra: Vec<(&'static str, Value)>) -> Vec<(&'static str, Value)> {
    let mut config = vec![
        ("materialized", Value::Str("snapshot")),
        ("unique_key", Value::Str("order_id")),
        ("snapshot_strategy", Value::Str("timestamp")),
        ("updated_at", Value::Str("updated_at")),
    ];
    config.extend(extra);
    config
}
