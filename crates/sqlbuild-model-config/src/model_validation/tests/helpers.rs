use crate::errors::ConfigError;
use crate::model_validation::main::validate_model_config::validate_model_config;
use crate::model_validation::models::{
    ModelReference, ModelValidationFacts, ProjectValidationFacts, ValidationStop,
};
use crate::tests::test_types::Value;

/// The validator error `model 'orders_daily': <text>`.
pub(super) fn validator_error(text: &str) -> ValidationStop {
    ValidationStop::Error(ConfigError::compile(format!(
        "model 'orders_daily': {text}"
    )))
}

/// Validate `config` for `orders_daily`: `accepted`, `deferred`, or the error message.
pub(super) fn validation_outcome(
    config: Vec<(&'static str, Value)>,
    references: &[&str],
    query_sql: &str,
) -> String {
    let references: Vec<ModelReference> = references
        .iter()
        .filter_map(|reference| reference.split_once(':'))
        .map(|(kind, name)| ModelReference {
            kind: kind.to_owned(),
            name: name.to_owned(),
        })
        .collect();
    let facts = ModelValidationFacts {
        model_name: "orders_daily",
        relative_path: "models/marts/orders_daily.sql",
        references: &references,
        declared_columns: None,
        query_sql,
        retention_unmanaged: true,
        table_type_declared: false,
    };
    let entries: Vec<(Value, Value)> = config
        .into_iter()
        .map(|(key, value)| (Value::Str(key), value))
        .collect();
    validate_model_config(entries, &project(), &facts)
        .map_or_else(stop_text, |()| "accepted".to_owned())
}

fn stop_text(stop: ValidationStop) -> String {
    let ValidationStop::Error(error) = stop else {
        return "deferred".to_owned();
    };
    error.message
}

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
