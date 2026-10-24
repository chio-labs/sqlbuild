//! A SQL macro's declared `returns` type checked against the adapter's SQL analysis dialect.

use polyglot_sql::expressions::DataType;
use polyglot_sql::{Dialect, DialectType, Expression};

use crate::sql_macros::_helpers::typing::returns_check::adapter_dialect;
use crate::sql_macros::constants::{
    BIGQUERY_BIG_DECIMAL_NAMES, BIGQUERY_BIGNUMERIC_LIMITS, BIGQUERY_NUMERIC_LIMITS,
};

/// Why `returns` is not a type the adapter's SQL analysis dialect parses and can hold.
pub(crate) fn returns_type_error(returns: &str, adapter: &str, context: &str) -> Option<String> {
    let dialect_name: &str = adapter_dialect(adapter);
    let Ok(dialect) = dialect_name.parse::<DialectType>() else {
        return None;
    };
    let reason: String = match polyglot_sql::parse_data_type(returns, dialect) {
        Ok(parsed) => decimal_error(&parsed, dialect)
            .or_else(|| bigquery_numeric_error(returns, &parsed, dialect))?,
        Err(error) => error.to_string(),
    };
    Some(format!(
        "{context} type '{returns}' is not valid for adapter '{adapter}' SQL analysis dialect \
         '{dialect_name}': {reason}"
    ))
}

/// Why a BigQuery `NUMERIC(P, S)` or `BIGNUMERIC(P, S)` has more digits than the type holds.
fn bigquery_numeric_error(
    type_sql: &str,
    data_type: &DataType,
    dialect: DialectType,
) -> Option<String> {
    let DataType::Decimal {
        precision: Some(precision),
        scale,
    } = data_type
    else {
        return None;
    };
    if dialect != DialectType::BigQuery {
        return None;
    }
    let scale: u32 = scale.unwrap_or(0);
    let big: bool = BIGQUERY_BIG_DECIMAL_NAMES
        .iter()
        .any(|name| type_sql.trim_start().to_ascii_uppercase().starts_with(name));
    let (max_integer_digits, max_scale) = if big {
        BIGQUERY_BIGNUMERIC_LIMITS
    } else {
        BIGQUERY_NUMERIC_LIMITS
    };
    let integer_digits: u32 = precision.saturating_sub(scale);
    (integer_digits > max_integer_digits || scale > max_scale).then(|| {
        format!(
            "precision {precision} and scale {scale} exceed BigQuery's limits of {max_integer_digits} \
             integer digits and scale {max_scale}"
        )
    })
}

/// Why a decimal within `data_type` has a precision or scale `dialect` cannot hold.
fn decimal_error(data_type: &DataType, dialect: DialectType) -> Option<String> {
    match data_type {
        DataType::Decimal {
            precision: Some(precision),
            scale,
        } => {
            if let Some(scale) = scale.filter(|scale| scale > precision) {
                return Some(format!(
                    "DECIMAL scale {scale} is larger than its precision {precision}"
                ));
            }
            match Dialect::get(dialect).generate(&Expression::DataType(data_type.clone())) {
                Ok(_) => None,
                Err(polyglot_sql::error::Error::Unsupported { feature, .. }) => Some(feature),
                Err(_) => None,
            }
        }
        DataType::Array { element_type, .. } | DataType::List { element_type } => {
            decimal_error(element_type, dialect)
        }
        DataType::Nullable { inner } => decimal_error(inner, dialect),
        DataType::Map {
            key_type,
            value_type,
        } => decimal_error(key_type, dialect).or_else(|| decimal_error(value_type, dialect)),
        DataType::Struct { fields, .. } => fields
            .iter()
            .find_map(|field| decimal_error(&field.data_type, dialect)),
        _ => None,
    }
}
