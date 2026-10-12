//! Python reprs of normalized values: `sql_value_identity` keys and `SqlValue` payloads.

use crate::sql_values::_helpers::decimals::{normalized_parts, parse_decimal};
use crate::sql_values::errors::SqlValueFailure;
use sqlbuild_core::json::main::python_float_repr::python_float_repr;
use sqlbuild_core::models::{SqlLogicalType, SqlValue};
use sqlbuild_core::text::main::python_str_repr::python_str_repr;

fn text_repr(text: &str) -> String {
    python_str_repr(text)
}

/// `repr(tuple(items))`, with the trailing comma of a one-item tuple.
fn tuple_repr(items: &[String]) -> String {
    match items {
        [only] => format!("({only},)"),
        _ => format!("({})", items.join(", ")),
    }
}

fn bool_repr(flag: bool) -> &'static str {
    if flag { "True" } else { "False" }
}

fn decimal_tuple_repr(text: &str) -> Result<String, SqlValueFailure> {
    let number = parse_decimal(text).ok_or_else(|| SqlValueFailure::Invalid(text.to_owned()))?;
    let (negative, digits, exponent) = normalized_parts(&number)?;
    let digits: Vec<String> = digits.chars().map(String::from).collect();
    Ok(format!(
        "DecimalTuple(sign={}, digits={}, exponent={exponent})",
        u8::from(negative),
        tuple_repr(&digits)
    ))
}

/// `repr(sql_value_identity(value=value))`; the text orders and deduplicates set members.
pub(crate) fn identity_repr(value: &SqlValue) -> Result<String, SqlValueFailure> {
    let kind = value.logical_type().kind.as_str();
    let payload = match value {
        SqlValue::Null => "None".to_owned(),
        SqlValue::Boolean(flag) => bool_repr(*flag).to_owned(),
        SqlValue::Integer(number) => number.to_string(),
        SqlValue::Float(number) => python_float_repr(*number),
        SqlValue::Decimal(text) => decimal_tuple_repr(text)?,
        SqlValue::String(text) => text_repr(text),
        SqlValue::List { values, .. } | SqlValue::Set { values, .. } => tuple_repr(
            &values
                .iter()
                .map(identity_repr)
                .collect::<Result<Vec<_>, _>>()?,
        ),
        SqlValue::Object(entries) => tuple_repr(
            &entries
                .iter()
                .map(|(key, item)| Ok(format!("({}, {})", text_repr(key), identity_repr(item)?)))
                .collect::<Result<Vec<_>, SqlValueFailure>>()?,
        ),
    };
    Ok(format!("('{kind}', {payload})"))
}

fn logical_repr(logical: &SqlLogicalType) -> String {
    let kind = logical.kind.as_str();
    let element = logical
        .element_type
        .as_deref()
        .map_or_else(|| "None".to_owned(), logical_repr);
    format!(
        "SqlLogicalType(kind=<SqlValueKind.{}: '{kind}'>, element_type={element})",
        kind.to_ascii_uppercase()
    )
}

fn sql_value_repr(value: &SqlValue) -> String {
    format!(
        "SqlValue(logical_type={}, value={})",
        logical_repr(&value.logical_type()),
        payload_repr(value)
    )
}

/// `repr(value.value)`.
pub(crate) fn payload_repr(value: &SqlValue) -> String {
    match value {
        SqlValue::Null => "None".to_owned(),
        SqlValue::Boolean(flag) => bool_repr(*flag).to_owned(),
        SqlValue::Integer(number) => number.to_string(),
        SqlValue::Float(number) => python_float_repr(*number),
        SqlValue::Decimal(text) => format!("Decimal('{text}')"),
        SqlValue::String(text) => text_repr(text),
        SqlValue::List { values, .. } | SqlValue::Set { values, .. } => {
            tuple_repr(&values.iter().map(sql_value_repr).collect::<Vec<_>>())
        }
        SqlValue::Object(entries) => tuple_repr(
            &entries
                .iter()
                .map(|(key, item)| format!("({}, {})", text_repr(key), sql_value_repr(item)))
                .collect::<Vec<_>>(),
        ),
    }
}
