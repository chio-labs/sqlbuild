//! Python's `_polyglot_expression_type` for one function argument expression.

use std::collections::HashMap;

use polyglot_sql::{DataType, Expression};
use serde_json::Value;

use crate::semantic_checks::_helpers::sql_text::text::upper;
use crate::semantic_checks::constants::{
    BOOLEAN_RESULT_KINDS, BOOLEAN_TYPE_NAME, COLUMN_KIND, CUSTOM_TYPE_NAME, DECIMAL_TYPE_NAME,
    KNOWN_CAST_TYPE_NAMES, TIMESTAMP_KIND, TIMESTAMP_WITH_TIME_ZONE_TYPE_NAME, VARCHAR_DATA_TYPES,
};
use crate::semantic_checks::models::SemanticFailure;

/// The type Python infers for `expression`, or None.
pub(crate) fn expression_type(
    expression: &Expression,
    return_types: &HashMap<String, String>,
) -> Result<Option<String>, SemanticFailure> {
    let kind: &str = expression.variant_name();
    let name: &str = expression.get_name();
    let function_name: &str = if name.is_empty() { kind } else { name };
    if kind != COLUMN_KIND
        && let Some(declared) = return_types.get(&upper(function_name))
    {
        return Ok(Some(declared.clone()));
    }
    if BOOLEAN_RESULT_KINDS.contains(&kind) {
        return Ok(Some(BOOLEAN_TYPE_NAME.to_owned()));
    }
    match expression {
        Expression::Cast(cast) | Expression::TryCast(cast) => cast_type(&cast.to),
        _ => Ok(None),
    }
}

/// Python's reading of a cast's serialised `to` payload.
fn cast_type(data_type: &DataType) -> Result<Option<String>, SemanticFailure> {
    let target: Value = serde_json::to_value(data_type)
        .map_err(|_| SemanticFailure::internal("a cast type does not serialize"))?;
    let Some(raw_type) = target
        .get("data_type")
        .and_then(Value::as_str)
        .filter(|raw| !raw.is_empty())
    else {
        return Ok(None);
    };
    let custom_name: Option<&str> = target
        .get("name")
        .and_then(Value::as_str)
        .filter(|name| !name.is_empty());
    if raw_type.eq_ignore_ascii_case(CUSTOM_TYPE_NAME)
        && let Some(name) = custom_name
    {
        return Ok(Some(upper(name)));
    }
    let lowered: String = raw_type.to_ascii_lowercase();
    if lowered == TIMESTAMP_KIND && target.get("timezone") == Some(&Value::Bool(true)) {
        return Ok(Some(TIMESTAMP_WITH_TIME_ZONE_TYPE_NAME.to_owned()));
    }
    let type_name: String = KNOWN_CAST_TYPE_NAMES
        .iter()
        .find(|(raw, _)| *raw == raw_type)
        .map_or_else(
            || raw_type.replace('_', " ").to_ascii_uppercase(),
            |(_, known)| (*known).to_owned(),
        );
    if VARCHAR_DATA_TYPES.contains(&lowered.as_str())
        && let Some(length) = integer(&target, "length")
    {
        return Ok(Some(format!("VARCHAR({length})")));
    }
    if type_name == DECIMAL_TYPE_NAME
        && let Some(precision) = integer(&target, "precision")
    {
        return Ok(Some(match integer(&target, "scale") {
            Some(scale) => format!("DECIMAL({precision}, {scale})"),
            None => format!("DECIMAL({precision})"),
        }));
    }
    Ok(Some(type_name))
}

/// Python's `isinstance(target.get(key), int)` value.
fn integer(target: &Value, key: &str) -> Option<i128> {
    let value: &Value = target.get(key)?;
    value
        .as_i64()
        .map(i128::from)
        .or_else(|| value.as_u64().map(i128::from))
}
