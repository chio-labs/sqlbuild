//! Python's `build_sql_test_case_fingerprint`: the version identity of one expanded test case.

use sha2::{Digest, Sha256};
use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::compiler::models::{
    SqlTestAssemblyDeferral, SqlTestAssemblyTest, SqlTestParameterValue,
};

/// Python's default decimal context: precision and exponent limits `normalize()` applies.
const DECIMAL_PRECISION: usize = 28;
const DECIMAL_EMAX: i64 = 999_999;
const DECIMAL_EMIN: i64 = -999_999;

/// The SHA-256 of Python's compact, ASCII, key-sorted JSON of the case's compile inputs.
pub(crate) fn case_fingerprint(
    test: &SqlTestAssemblyTest,
    case_name: &str,
    scope_deps: &[(&'static str, String)],
    tested_resources: &[(String, String)],
) -> Result<String, SqlTestAssemblyDeferral> {
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
        .collect::<Result<_, SqlTestAssemblyDeferral>>()?;
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
    let encoded =
        dumps(&payload, &dialect).map_err(|_| SqlTestAssemblyDeferral::UnencodableValue)?;
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
fn identity(value: &SqlTestParameterValue) -> Result<JsonValue, SqlTestAssemblyDeferral> {
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
                    .collect::<Result<_, SqlTestAssemblyDeferral>>()?,
            ),
        ),
    };
    Ok(JsonValue::Array(vec![string(kind), payload]))
}

fn identities(items: &[SqlTestParameterValue]) -> Result<JsonValue, SqlTestAssemblyDeferral> {
    Ok(JsonValue::Array(
        items.iter().map(identity).collect::<Result<_, _>>()?,
    ))
}

/// `Decimal.normalize().as_tuple()` where the default context neither rounds nor clamps.
fn normalized_decimal(
    negative: bool,
    digits: &[u8],
    exponent: i64,
) -> Result<JsonValue, SqlTestAssemblyDeferral> {
    let sign = integer(i64::from(negative));
    let first = digits.iter().position(|digit| *digit != 0);
    let Some(first) = first else {
        return Ok(JsonValue::Array(vec![
            sign,
            JsonValue::Array(vec![integer(0)]),
            integer(0),
        ]));
    };
    let significant = &digits[first..];
    let adjusted = exponent + i64::try_from(significant.len()).unwrap_or(i64::MAX) - 1;
    if significant.len() > DECIMAL_PRECISION || !(DECIMAL_EMIN..=DECIMAL_EMAX).contains(&adjusted) {
        return Err(SqlTestAssemblyDeferral::DecimalContext);
    }
    let mut end = significant.len();
    let mut normalized_exponent = exponent;
    while significant[end - 1] == 0 && normalized_exponent < DECIMAL_EMAX {
        end -= 1;
        normalized_exponent += 1;
    }
    Ok(JsonValue::Array(vec![
        sign,
        JsonValue::Array(
            significant[..end]
                .iter()
                .map(|digit| integer(i64::from(*digit)))
                .collect(),
        ),
        integer(normalized_exponent),
    ]))
}
