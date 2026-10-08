//! Python's `_normalize_with_polyglot`: the parsed type's SQL and arguments.

use polyglot_sql::ast_json::{expression_from_value, expressions_from_value};
use polyglot_sql::{ComplexityGuardOptions, DataType, Dialect, Expression, ParseOptions};
use serde_json::{Map, Value};

use crate::type_system::_helpers::fallback::{
    normalize_with_fallback, python_or_default, simple, snowflake_integer,
    timestamp_normalized_name,
};
use crate::type_system::_helpers::python_text::split_type_and_params;
use crate::type_system::constants::{
    BIGNUMERIC_TYPE_NAME, BOOLEAN_TYPE_NAMES, CUSTOM_NORMALIZATION_TYPE_NAMES, DATE_TYPE_NAME,
    DATETIME_TYPE_NAME, DECIMAL_TYPE_NAMES, FLOAT_TYPE_NAMES, FLOAT_WIRE_TYPE_NAME,
    INTEGER_PARSE_TYPE_NAMES, INTEGER_PRECISION, INTEGER_SCALE, INTEGER_TYPE_NAMES,
    MAX_FUNCTION_CALL_DEPTH, POLYGLOT_CUSTOM_TYPE_NAME, POLYGLOT_TYPE_NAME_ALIASES,
    STRING_TYPE_NAMES, TIMESTAMP_TYPE_NAMES, UNBOUNDED_TEXT_TYPE_NAMES,
};
use crate::type_system::models::{NormalizedType, TypeDialect, TypeFamily};

/// Parse one type with SQLBuild's Polyglot guard; the error text is what Python logs.
pub(crate) fn parse_type(type_sql: &str, dialect: &Dialect) -> Result<DataType, String> {
    dialect
        .parse_data_type_with_options(
            type_sql,
            &ParseOptions {
                complexity_guard: Some(ComplexityGuardOptions {
                    max_function_call_depth: Some(MAX_FUNCTION_CALL_DEPTH),
                    ..Default::default()
                }),
            },
        )
        .map_err(|error| error.to_string())
}

/// Python's `_normalized_from_parsed_type`, or None where Python raises or holds an object.
pub(crate) fn normalize_parsed(
    parsed: DataType,
    polyglot: &Dialect,
    dialect: Option<TypeDialect>,
) -> Option<NormalizedType> {
    let expression: Expression = Expression::DataType(parsed);
    let Ok(generated) = polyglot.generate(&expression) else {
        return None;
    };
    if !generated.is_ascii() {
        return None;
    }
    let normalized_name: String = generated.to_ascii_uppercase().replace(' ', "");
    let args: Map<String, Value> = expression_args(&expression)?;
    let dtype_name: String = polyglot_type_name(&args)?;
    let params: Vec<i64> = polyglot_type_params(&args)?;
    let snowflake: bool = dialect == Some(TypeDialect::Snowflake);
    let bigquery: bool = dialect == Some(TypeDialect::BigQuery);
    let dtype: &str = dtype_name.as_str();

    if bigquery && INTEGER_PARSE_TYPE_NAMES.contains(&dtype) {
        return Some(simple("INT64", TypeFamily::Integer));
    }
    if bigquery && dtype == BIGNUMERIC_TYPE_NAME {
        return Some(simple("BIGNUMERIC", TypeFamily::Decimal));
    }
    if bigquery && dtype == FLOAT_WIRE_TYPE_NAME {
        return Some(simple("FLOAT64", TypeFamily::Float));
    }
    if dtype == POLYGLOT_CUSTOM_TYPE_NAME {
        let raw_name: String = match args.get("name") {
            Some(value) => python_str(value)?,
            None => normalized_name.clone(),
        }
        .to_ascii_uppercase()
        .replace(' ', "");
        if snowflake && raw_name.starts_with("NUMBER") {
            return snowflake_number(&raw_name);
        }
        return normalize_with_fallback(&raw_name, dialect);
    }
    if INTEGER_TYPE_NAMES.contains(&dtype) {
        if snowflake {
            return Some(snowflake_integer());
        }
        return Some(simple(&normalized_name, TypeFamily::Integer));
    }
    if DECIMAL_TYPE_NAMES.contains(&dtype) {
        let mut precision: Option<i64> = params.first().copied();
        let mut scale: Option<i64> = params.get(1).copied();
        let mut name: String = normalized_name;
        if snowflake && precision.is_none() {
            precision = Some(INTEGER_PRECISION);
            scale = Some(INTEGER_SCALE);
            name = format!("DECIMAL({INTEGER_PRECISION},{INTEGER_SCALE})");
        }
        return Some(NormalizedType {
            normalized_name: name,
            family: TypeFamily::Decimal,
            precision,
            scale,
            length: None,
        });
    }
    if FLOAT_TYPE_NAMES.contains(&dtype) {
        return Some(simple(&normalized_name, TypeFamily::Float));
    }
    if STRING_TYPE_NAMES.contains(&dtype) {
        let mut length: Option<i64> = params.first().copied();
        let mut name: String = normalized_name;
        let base_name: &str = name.split('(').next().unwrap_or_default();
        if snowflake && UNBOUNDED_TEXT_TYPE_NAMES.contains(&base_name) {
            let bounded: i64 = python_or_default(length);
            length = Some(bounded);
            name = format!("VARCHAR({bounded})");
        }
        return Some(NormalizedType {
            normalized_name: name,
            family: TypeFamily::String,
            precision: None,
            scale: None,
            length,
        });
    }
    if BOOLEAN_TYPE_NAMES.contains(&dtype) {
        return Some(simple(&normalized_name, TypeFamily::Boolean));
    }
    if TIMESTAMP_TYPE_NAMES.contains(&dtype) {
        return Some(simple(
            &timestamp_normalized_name(&normalized_name, dialect),
            TypeFamily::Timestamp,
        ));
    }
    if dtype == DATE_TYPE_NAME {
        return Some(simple(&normalized_name, TypeFamily::Date));
    }
    if dtype == DATETIME_TYPE_NAME {
        return Some(simple(&normalized_name, TypeFamily::Datetime));
    }
    Some(simple(&normalized_name, TypeFamily::Other))
}

/// Snowflake's `NUMBER(p,s)` spelled as a custom type: Python's `DECIMAL` rewrite.
fn snowflake_number(raw_name: &str) -> Option<NormalizedType> {
    let mut decimal_name: String = raw_name.replacen("NUMBER", "DECIMAL", 1);
    let (_, params) = split_type_and_params(&decimal_name)?;
    let mut precision: Option<i64> = params.first().copied();
    let mut scale: Option<i64> = params.get(1).copied();
    if precision.is_none() {
        precision = Some(INTEGER_PRECISION);
        scale = Some(INTEGER_SCALE);
        decimal_name = format!("DECIMAL({INTEGER_PRECISION},{INTEGER_SCALE})");
    }
    Some(NormalizedType {
        normalized_name: decimal_name,
        family: TypeFamily::Decimal,
        precision,
        scale,
        length: None,
    })
}

/// The wheel's `Expression.args`: the serde payload of the expression's variant.
fn expression_args(expression: &Expression) -> Option<Map<String, Value>> {
    let Ok(value) = serde_json::to_value(expression) else {
        return None;
    };
    match value {
        Value::Object(map) => match map.into_iter().next() {
            Some((_, Value::Object(payload))) => Some(payload),
            _ => Some(Map::new()),
        },
        _ => Some(Map::new()),
    }
}

/// Python's `_polyglot_type_name`.
fn polyglot_type_name(args: &Map<String, Value>) -> Option<String> {
    let data_type: String = match args.get("data_type") {
        Some(value) => python_str(value)?,
        None => String::new(),
    }
    .to_ascii_uppercase();
    if let Some((_, alias)) = POLYGLOT_TYPE_NAME_ALIASES
        .iter()
        .find(|(name, _)| *name == data_type)
    {
        return Some((*alias).to_owned());
    }
    if data_type == POLYGLOT_CUSTOM_TYPE_NAME {
        let name: String = match args.get("name") {
            Some(value) => python_str(value)?,
            None => String::new(),
        }
        .to_ascii_uppercase()
        .replace(' ', "");
        if CUSTOM_NORMALIZATION_TYPE_NAMES.contains(&name.as_str()) {
            return Some(name);
        }
    }
    Some(data_type)
}

/// Python's `_polyglot_type_params`; text and integers beyond `i64` defer.
fn polyglot_type_params(args: &Map<String, Value>) -> Option<Vec<i64>> {
    let mut params: Vec<i64> = Vec::new();
    for key in ["precision", "scale", "length"] {
        let Some(value) = args.get(key) else {
            continue;
        };
        match value {
            Value::Null | Value::Array(_) | Value::Object(_) => {}
            Value::Bool(flag) => params.push(i64::from(*flag)),
            Value::Number(number) => params.push(number.as_i64()?),
            Value::String(_) if is_python_expression(value) => {}
            Value::String(_) => return None,
        }
    }
    Some(params)
}

/// Python's `str(value)` for the text values Polyglot returns; None for anything else.
fn python_str(value: &Value) -> Option<String> {
    if is_python_expression(value) {
        return None;
    }
    match value {
        Value::String(text) if text.is_ascii() => Some(text.clone()),
        Value::Null => Some("None".to_owned()),
        _ => None,
    }
}

/// Whether the wheel hands Python this value as an expression object rather than data.
fn is_python_expression(value: &Value) -> bool {
    if let Ok(_expression) = expression_from_value(value.clone()) {
        return true;
    }
    let Ok(_expressions) = expressions_from_value(value.clone()) else {
        return false;
    };
    true
}
