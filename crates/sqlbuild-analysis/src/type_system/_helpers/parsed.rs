//! Python's `_normalize_with_polyglot`: the parsed type's SQL and arguments.

use polyglot_sql::{ComplexityGuardOptions, DataType, Dialect, Expression, ParseOptions};
use serde_json::{Map, Value};

use crate::type_system::_helpers::fallback::{
    normalize_with_fallback, python_or_default, simple, snowflake_integer,
    timestamp_normalized_name,
};
use crate::type_system::_helpers::python_text::{python_int, split_type_and_params, upper};
use crate::type_system::constants::{
    BIGNUMERIC_TYPE_NAME, BOOLEAN_TYPE_NAMES, CUSTOM_NORMALIZATION_TYPE_NAMES, DATE_TYPE_NAME,
    DATETIME_TYPE_NAME, DECIMAL_TYPE_NAMES, FLOAT_TYPE_NAMES, FLOAT_WIRE_TYPE_NAME,
    INTEGER_PARSE_TYPE_NAMES, INTEGER_PRECISION, INTEGER_SCALE, INTEGER_TYPE_NAMES,
    MAX_FUNCTION_CALL_DEPTH, POLYGLOT_CUSTOM_TYPE_NAME, POLYGLOT_TYPE_NAME_ALIASES,
    STRING_TYPE_NAMES, TIMESTAMP_TYPE_NAMES, UNBOUNDED_TEXT_TYPE_NAMES,
};
use crate::type_system::models::{
    NormalizedType, PythonInteger, TypeDialect, TypeFamily, TypeNormalizationError,
};

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

/// Python's `_normalized_from_parsed_type`.
pub(crate) fn normalize_parsed(
    parsed: DataType,
    polyglot: &Dialect,
    dialect: Option<TypeDialect>,
) -> Result<NormalizedType, TypeNormalizationError> {
    let expression: Expression = Expression::DataType(parsed);
    let generated: String = polyglot
        .generate(&expression)
        .map_err(|error| TypeNormalizationError::Generation(error.to_string()))?;
    let normalized_name: String = upper(&generated).replace(' ', "");
    let args: Map<String, Value> = expression_args(&expression);
    let dtype_name: String = polyglot_type_name(&args);
    let params: Vec<PythonInteger> = polyglot_type_params(&args);
    let snowflake: bool = dialect == Some(TypeDialect::Snowflake);
    let bigquery: bool = dialect == Some(TypeDialect::BigQuery);
    let dtype: &str = dtype_name.as_str();

    if bigquery && INTEGER_PARSE_TYPE_NAMES.contains(&dtype) {
        return Ok(simple("INT64", TypeFamily::Integer));
    }
    if bigquery && dtype == BIGNUMERIC_TYPE_NAME {
        return Ok(simple("BIGNUMERIC", TypeFamily::Decimal));
    }
    if bigquery && dtype == FLOAT_WIRE_TYPE_NAME {
        return Ok(simple("FLOAT64", TypeFamily::Float));
    }
    if dtype == POLYGLOT_CUSTOM_TYPE_NAME {
        let raw_name: String = upper(&match args.get("name") {
            Some(value) => python_str(value),
            None => normalized_name.clone(),
        })
        .replace(' ', "");
        if snowflake && raw_name.starts_with("NUMBER") {
            return Ok(snowflake_number(&raw_name));
        }
        return Ok(normalize_with_fallback(&raw_name, dialect));
    }
    if INTEGER_TYPE_NAMES.contains(&dtype) {
        if snowflake {
            return Ok(snowflake_integer());
        }
        return Ok(simple(&normalized_name, TypeFamily::Integer));
    }
    if DECIMAL_TYPE_NAMES.contains(&dtype) {
        let mut precision: Option<PythonInteger> = params.first().cloned();
        let mut scale: Option<PythonInteger> = params.get(1).cloned();
        let mut name: String = normalized_name;
        if snowflake && precision.is_none() {
            precision = Some(INTEGER_PRECISION.into());
            scale = Some(INTEGER_SCALE.into());
            name = format!("DECIMAL({INTEGER_PRECISION},{INTEGER_SCALE})");
        }
        return Ok(NormalizedType {
            normalized_name: name,
            family: TypeFamily::Decimal,
            precision,
            scale,
            length: None,
        });
    }
    if FLOAT_TYPE_NAMES.contains(&dtype) {
        return Ok(simple(&normalized_name, TypeFamily::Float));
    }
    if STRING_TYPE_NAMES.contains(&dtype) {
        let mut length: Option<PythonInteger> = params.first().cloned();
        let mut name: String = normalized_name;
        let base_name: &str = name.split('(').next().unwrap_or_default();
        if snowflake && UNBOUNDED_TEXT_TYPE_NAMES.contains(&base_name) {
            let bounded: PythonInteger = python_or_default(length);
            name = format!("VARCHAR({bounded})");
            length = Some(bounded);
        }
        return Ok(NormalizedType {
            normalized_name: name,
            family: TypeFamily::String,
            precision: None,
            scale: None,
            length,
        });
    }
    if BOOLEAN_TYPE_NAMES.contains(&dtype) {
        return Ok(simple(&normalized_name, TypeFamily::Boolean));
    }
    if TIMESTAMP_TYPE_NAMES.contains(&dtype) {
        return Ok(simple(
            &timestamp_normalized_name(&normalized_name, dialect),
            TypeFamily::Timestamp,
        ));
    }
    if dtype == DATE_TYPE_NAME {
        return Ok(simple(&normalized_name, TypeFamily::Date));
    }
    if dtype == DATETIME_TYPE_NAME {
        return Ok(simple(&normalized_name, TypeFamily::Datetime));
    }
    Ok(simple(&normalized_name, TypeFamily::Other))
}

/// Snowflake's `NUMBER(p,s)` spelled as a custom type: Python's `DECIMAL` rewrite.
fn snowflake_number(raw_name: &str) -> NormalizedType {
    let mut decimal_name: String = raw_name.replacen("NUMBER", "DECIMAL", 1);
    let (_, params) = split_type_and_params(&decimal_name);
    let mut precision: Option<PythonInteger> = params.first().cloned();
    let mut scale: Option<PythonInteger> = params.get(1).cloned();
    if precision.is_none() {
        precision = Some(INTEGER_PRECISION.into());
        scale = Some(INTEGER_SCALE.into());
        decimal_name = format!("DECIMAL({INTEGER_PRECISION},{INTEGER_SCALE})");
    }
    NormalizedType {
        normalized_name: decimal_name,
        family: TypeFamily::Decimal,
        precision,
        scale,
        length: None,
    }
}

/// The wheel's `Expression.args`: the serde payload of the expression's variant.
fn expression_args(expression: &Expression) -> Map<String, Value> {
    match serde_json::to_value(expression) {
        Ok(Value::Object(map)) => match map.into_iter().next() {
            Some((_, Value::Object(payload))) => payload,
            _ => Map::new(),
        },
        _ => Map::new(),
    }
}

/// Python's `_polyglot_type_name`.
fn polyglot_type_name(args: &Map<String, Value>) -> String {
    let data_type: String = upper(&match args.get("data_type") {
        Some(value) => python_str(value),
        None => String::new(),
    });
    if let Some((_, alias)) = POLYGLOT_TYPE_NAME_ALIASES
        .iter()
        .find(|(name, _)| *name == data_type)
    {
        return (*alias).to_owned();
    }
    if data_type == POLYGLOT_CUSTOM_TYPE_NAME {
        let name: String = upper(&match args.get("name") {
            Some(value) => python_str(value),
            None => String::new(),
        })
        .replace(' ', "");
        if CUSTOM_NORMALIZATION_TYPE_NAMES.contains(&name.as_str()) {
            return name;
        }
    }
    data_type
}

/// Python's `_polyglot_type_params`: `int(value)` of each present parameter, skipping what
/// `int` rejects.
fn polyglot_type_params(args: &Map<String, Value>) -> Vec<PythonInteger> {
    let mut params: Vec<PythonInteger> = Vec::new();
    for key in ["precision", "scale", "length"] {
        let Some(value) = args.get(key) else {
            continue;
        };
        let param: Option<PythonInteger> = match value {
            Value::Null | Value::Array(_) | Value::Object(_) => None,
            Value::Bool(flag) => Some(i64::from(*flag).into()),
            Value::Number(number) => python_int(&number.to_string()),
            Value::String(text) => python_int(text),
        };
        params.extend(param);
    }
    params
}

/// Python's `str(value)` for the scalar values Polyglot gives a parsed type's tag and name.
fn python_str(value: &Value) -> String {
    match value {
        Value::String(text) => text.clone(),
        Value::Null => "None".to_owned(),
        Value::Bool(true) => "True".to_owned(),
        Value::Bool(false) => "False".to_owned(),
        Value::Number(number) => number.to_string(),
        Value::Array(_) | Value::Object(_) => value.to_string(),
    }
}
