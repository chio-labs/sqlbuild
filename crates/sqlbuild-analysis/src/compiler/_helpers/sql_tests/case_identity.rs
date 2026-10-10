//! Python's `build_sql_test_case_fingerprint`: the version identity of one expanded test case.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::compiler::models::{SqlTestAssemblyTest, SqlTestParameterValue};

/// Why Python's fingerprint of a case raises.
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum FingerprintFailure {
    /// `Decimal.normalize()` overflows the default context: Python raises `decimal.Overflow`.
    DecimalOverflow,
    /// An internal native failure.
    Internal(String),
}

/// Python's default decimal context: precision and exponent limits `normalize()` applies.
const DECIMAL_PRECISION: usize = 28;
const DECIMAL_EMAX: i64 = 999_999;
const DECIMAL_EMIN: i64 = -999_999;
/// The smallest exponent of a subnormal result: `Emin - prec + 1`.
const DECIMAL_ETINY: i64 = DECIMAL_EMIN - 27;

/// The SHA-256 of Python's compact, ASCII, key-sorted JSON of the case's compile inputs.
pub(crate) fn case_fingerprint(
    test: &SqlTestAssemblyTest,
    case_name: &str,
    scope_deps: &[(&'static str, String)],
    tested_resources: &[(String, String)],
) -> Result<String, FingerprintFailure> {
    let mut sorted_deps: Vec<(&str, &str)> = scope_deps
        .iter()
        .map(|(kind, name)| (*kind, name.as_str()))
        .collect();
    sorted_deps.sort_unstable();
    let mut sorted_resources: Vec<(&str, &str)> = tested_resources
        .iter()
        .map(|(kind, name)| (kind.as_str(), name.as_str()))
        .collect();
    sorted_resources.sort_unstable();
    let parameter_values: Vec<JsonValue> = test
        .parameter_values
        .iter()
        .map(|(name, value)| Ok(JsonValue::Array(vec![string(name), identity(value)?])))
        .collect::<Result<_, FingerprintFailure>>()?;
    let payload = JsonValue::Object(vec![
        ("source_path".to_owned(), string(&test.relative_path)),
        ("block_index".to_owned(), integer(test.block_index)),
        ("case_name".to_owned(), string(case_name)),
        (
            "parameter_schema".to_owned(),
            JsonValue::Array(
                test.parameter_schema
                    .iter()
                    .map(|(name, kind, nullable)| {
                        JsonValue::Array(vec![
                            string(name),
                            string(kind),
                            JsonValue::Bool(*nullable),
                        ])
                    })
                    .collect(),
            ),
        ),
        (
            "parameter_values".to_owned(),
            JsonValue::Array(parameter_values),
        ),
        ("expanded_sql".to_owned(), string(&test.sql_body)),
        ("scope_deps".to_owned(), pairs(&sorted_deps)),
        ("tested_resources".to_owned(), pairs(&sorted_resources)),
    ]);
    let dialect = JsonDialect::Stdlib(StdlibJsonOptions {
        indent: None,
        item_separator: ",".to_owned(),
        key_separator: ":".to_owned(),
        ensure_ascii: true,
        sort_keys: true,
        allow_nan: true,
    });
    let encoded = dumps(&payload, &dialect).map_err(|error| {
        FingerprintFailure::Internal(format!(
            "the case fingerprint payload does not encode: {error:?}"
        ))
    })?;
    Ok(Sha256::digest(encoded.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn string(text: &str) -> JsonValue {
    JsonValue::String(text.to_owned())
}

fn integer(value: i64) -> JsonValue {
    JsonInteger::parse(&value.to_string()).map_or(JsonValue::Null, JsonValue::Integer)
}

fn pairs(entries: &[(&str, &str)]) -> JsonValue {
    JsonValue::Array(
        entries
            .iter()
            .map(|(first, second)| JsonValue::Array(vec![string(first), string(second)]))
            .collect(),
    )
}

/// Python's `sql_value_identity`: `(kind, payload)` with decimals as normalized tuples.
fn identity(value: &SqlTestParameterValue) -> Result<JsonValue, FingerprintFailure> {
    let (kind, payload) = match value {
        SqlTestParameterValue::String(text) => ("string", string(text)),
        SqlTestParameterValue::Integer(number) => ("integer", integer(*number)),
        SqlTestParameterValue::Boolean(flag) => ("boolean", JsonValue::Bool(*flag)),
        SqlTestParameterValue::Float(number) => ("float", JsonValue::Float(*number)),
        SqlTestParameterValue::Decimal {
            negative,
            digits,
            exponent,
        } => ("decimal", normalized_decimal(*negative, digits, *exponent)?),
        SqlTestParameterValue::Null => ("null", JsonValue::Null),
        SqlTestParameterValue::List(items) => ("list", identities(items)?),
        SqlTestParameterValue::Set(items) => ("set", identities(items)?),
        SqlTestParameterValue::Object(entries) => (
            "object",
            JsonValue::Array(
                entries
                    .iter()
                    .map(|(key, item)| Ok(JsonValue::Array(vec![string(key), identity(item)?])))
                    .collect::<Result<_, FingerprintFailure>>()?,
            ),
        ),
    };
    Ok(JsonValue::Array(vec![string(kind), payload]))
}

fn identities(items: &[SqlTestParameterValue]) -> Result<JsonValue, FingerprintFailure> {
    Ok(JsonValue::Array(
        items.iter().map(identity).collect::<Result<_, _>>()?,
    ))
}

/// `Decimal.normalize().as_tuple()` under Python's default context: rounded half-even to its
/// precision, or to the subnormal exponent floor, then stripped of trailing zeros.
fn normalized_decimal(
    negative: bool,
    digits: &[u8],
    exponent: i64,
) -> Result<JsonValue, FingerprintFailure> {
    let sign = integer(i64::from(negative));
    let zero = || {
        JsonValue::Array(vec![
            integer(i64::from(negative)),
            JsonValue::Array(vec![integer(0)]),
            integer(0),
        ])
    };
    let Some(first) = digits.iter().position(|digit| *digit != 0) else {
        return Ok(zero());
    };
    let mut coefficient: Vec<u8> = digits[first..].to_vec();
    let mut exponent: i64 = exponent;
    let length = |coefficient: &[u8]| i64::try_from(coefficient.len()).unwrap_or(i64::MAX);
    let adjusted: i64 = exponent.saturating_add(length(&coefficient) - 1);
    let dropped: i64 = if adjusted < DECIMAL_EMIN {
        DECIMAL_ETINY.saturating_sub(exponent).max(0)
    } else {
        (length(&coefficient) - i64::try_from(DECIMAL_PRECISION).unwrap_or(i64::MAX)).max(0)
    };
    if dropped > 0 {
        coefficient =
            rounded_half_even(&coefficient, usize::try_from(dropped).unwrap_or(usize::MAX));
        exponent = exponent.saturating_add(dropped);
        if coefficient.len() > DECIMAL_PRECISION {
            let _ = coefficient.pop();
            exponent = exponent.saturating_add(1);
        }
        if coefficient.iter().all(|digit| *digit == 0) {
            return Ok(zero());
        }
    }
    if exponent.saturating_add(length(&coefficient) - 1) > DECIMAL_EMAX {
        return Err(FingerprintFailure::DecimalOverflow);
    }
    let mut end = coefficient.len();
    while coefficient[end - 1] == 0 && exponent < DECIMAL_EMAX {
        end -= 1;
        exponent += 1;
    }
    Ok(JsonValue::Array(vec![
        sign,
        JsonValue::Array(
            coefficient[..end]
                .iter()
                .map(|digit| integer(i64::from(*digit)))
                .collect(),
        ),
        integer(exponent),
    ]))
}

/// The coefficient without its last `dropped` digits, rounded half to even; a carry may add a
/// leading digit.
fn rounded_half_even(coefficient: &[u8], dropped: usize) -> Vec<u8> {
    if dropped > coefficient.len() {
        return vec![0];
    }
    let (kept, removed) = coefficient.split_at(coefficient.len() - dropped);
    let mut kept: Vec<u8> = if kept.is_empty() {
        vec![0]
    } else {
        kept.to_vec()
    };
    let round_up: bool = match removed.first() {
        Some(6..=9) => true,
        Some(5) => {
            removed[1..].iter().any(|digit| *digit != 0)
                || kept.last().is_some_and(|digit| digit % 2 == 1)
        }
        _ => false,
    };
    if round_up {
        let mut index = kept.len();
        loop {
            if index == 0 {
                kept.insert(0, 1);
                break;
            }
            index -= 1;
            if kept[index] == 9 {
                kept[index] = 0;
            } else {
                kept[index] += 1;
                break;
            }
        }
    }
    kept
}
