//! `_parse_test_parameters_and_cases`: declared parameters and their typed case values.

use crate::sql_tests::constants::{
    CASES_KEY, NULLABLE_OPTION, PARAMETER_TYPES, PARAMETERS_KEY, SQL_VALUE_KINDS, TYPE_OPTION,
};
use crate::sql_tests::models::{SqlTestCase, SqlTestParameter};
use crate::sql_values::errors::SqlValueFailure;
use crate::sql_values::main::normalize_sql_value::normalize_sql_value;
use crate::sql_values::models::{RawKey, RawSqlValue, SqlValueLimits};

type Entries = [(RawKey, RawSqlValue)];
type Parsed<T> = Result<T, String>;

/// The value of `key` in a header or option mapping.
pub(crate) fn entry<'a>(entries: &'a Entries, key: &str) -> Option<&'a RawSqlValue> {
    entries
        .iter()
        .find(|(candidate, _)| matches!(candidate, RawKey::Str(text) if text == key))
        .map(|(_, value)| value)
}

fn key_text(key: &RawKey) -> &str {
    match key {
        RawKey::Str(text) | RawKey::Other(text) => text,
    }
}

/// `^[A-Za-z_][A-Za-z0-9_]*$` under `fullmatch`.
pub(crate) fn is_identifier(text: &str) -> bool {
    let mut characters = text.chars();
    characters
        .next()
        .is_some_and(|first| first.is_ascii_alphabetic() || first == '_')
        && characters.all(|character| character.is_ascii_alphanumeric() || character == '_')
}

fn identifier(key: &RawKey, label: &str, file_path: &str) -> Parsed<String> {
    match key {
        RawKey::Str(text) if is_identifier(text) => Ok(text.clone()),
        _ => Err(format!(
            "TEST() {label} name in '{file_path}' must be a SQL identifier"
        )),
    }
}

fn non_empty_mapping<'a>(
    value: &'a RawSqlValue,
    label: &str,
    file_path: &str,
) -> Parsed<&'a Entries> {
    match value {
        RawSqlValue::Object(entries) if !entries.is_empty() => Ok(entries),
        _ => Err(format!(
            "TEST() {label} in '{file_path}' must be a non-empty mapping"
        )),
    }
}

fn declaration_options<'a>(
    options: &'a Entries,
    name: &str,
    file_path: &str,
) -> Parsed<(Option<&'a RawSqlValue>, bool)> {
    let mut unknown: Vec<&str> = options
        .iter()
        .map(|(key, _)| key_text(key))
        .filter(|key| *key != TYPE_OPTION && *key != NULLABLE_OPTION)
        .collect();
    unknown.sort_unstable();
    unknown.dedup();
    if !unknown.is_empty() {
        return Err(format!(
            "TEST() parameter '{name}' in '{file_path}' has unsupported options: {}",
            unknown.join(", ")
        ));
    }
    let nullable = match entry(options, NULLABLE_OPTION) {
        None => false,
        Some(RawSqlValue::Bool(flag)) => *flag,
        Some(_) => {
            return Err(format!(
                "TEST() parameter '{name}' nullable option in '{file_path}' must be boolean"
            ));
        }
    };
    Ok((entry(options, TYPE_OPTION), nullable))
}

fn parameter(key: &RawKey, declaration: &RawSqlValue, file_path: &str) -> Parsed<SqlTestParameter> {
    let name = identifier(key, "parameter", file_path)?;
    let (raw_type, nullable) = match declaration {
        RawSqlValue::Object(options) => declaration_options(options, &name, file_path)?,
        other => (Some(other), false),
    };
    let Some(RawSqlValue::Str(raw_type)) = raw_type else {
        return Err(format!(
            "TEST() parameter '{name}' type in '{file_path}' must be an identifier"
        ));
    };
    let lowered = raw_type.to_lowercase();
    if !SQL_VALUE_KINDS.contains(&lowered.as_str()) {
        return Err(format!(
            "TEST() parameter '{name}' in '{file_path}' has unsupported type '{raw_type}'"
        ));
    }
    let Some(value_type) = PARAMETER_TYPES.iter().find(|kind| **kind == lowered) else {
        return Err(format!(
            "TEST() parameter '{name}' in '{file_path}' must use a scalar type: {}",
            PARAMETER_TYPES.join(", ")
        ));
    };
    Ok(SqlTestParameter {
        name,
        value_type,
        nullable,
    })
}

fn case_value(
    parameter: &SqlTestParameter,
    raw: &RawSqlValue,
    case_name: &str,
    file_path: &str,
) -> Parsed<(String, sqlbuild_core::models::SqlValue)> {
    let label = format!(
        "TEST() case '{case_name}' parameter '{}' in '{file_path}'",
        parameter.name
    );
    let is_null = matches!(raw, RawSqlValue::Null);
    if is_null && !parameter.nullable {
        return Err(format!("{label} is not nullable"));
    }
    let explicit = (!is_null).then_some(parameter.value_type);
    normalize_sql_value(raw, &label, explicit, SqlValueLimits::default())
        .map(|value| (parameter.name.clone(), value))
        .map_err(|failure| match failure {
            SqlValueFailure::Invalid(message) => message,
            SqlValueFailure::DecimalOverflow => label,
        })
}

fn case(
    (key, raw_values): &(RawKey, RawSqlValue),
    parameters: &[SqlTestParameter],
    file_path: &str,
) -> Parsed<SqlTestCase> {
    let name = identifier(key, "case", file_path)?;
    let RawSqlValue::Object(values) = raw_values else {
        return Err(format!(
            "TEST() case '{name}' in '{file_path}' must define a parameter mapping"
        ));
    };
    let missing: Vec<&str> = parameters
        .iter()
        .map(|parameter| parameter.name.as_str())
        .filter(|parameter| entry(values, parameter).is_none())
        .collect();
    let extra: Vec<&str> = values
        .iter()
        .filter(|(key, _)| {
            !matches!(key, RawKey::Str(text) if parameters.iter().any(|parameter| parameter.name == *text))
        })
        .map(|(key, _)| key_text(key))
        .collect();
    if !missing.is_empty() {
        return Err(format!(
            "TEST() case '{name}' in '{file_path}' is missing parameters: {}",
            missing.join(", ")
        ));
    }
    if !extra.is_empty() {
        return Err(format!(
            "TEST() case '{name}' in '{file_path}' has undeclared parameters: {}",
            extra.join(", ")
        ));
    }
    let values = parameters
        .iter()
        .map(|parameter| {
            let raw = entry(values, &parameter.name).unwrap_or(&RawSqlValue::Null);
            case_value(parameter, raw, &name, file_path)
        })
        .collect::<Parsed<Vec<_>>>()?;
    Ok(SqlTestCase { name, values })
}

/// The declared parameters and cases of a TEST header, or why they are invalid.
pub(crate) fn parameters_and_cases(
    header: &Entries,
    file_path: &str,
) -> Parsed<(Vec<SqlTestParameter>, Vec<SqlTestCase>)> {
    let (raw_parameters, raw_cases) =
        match (entry(header, PARAMETERS_KEY), entry(header, CASES_KEY)) {
            (None | Some(RawSqlValue::Null), None | Some(RawSqlValue::Null)) => {
                return Ok((Vec::new(), Vec::new()));
            }
            (Some(parameters), Some(cases))
                if !matches!(parameters, RawSqlValue::Null)
                    && !matches!(cases, RawSqlValue::Null) =>
            {
                (parameters, cases)
            }
            _ => {
                return Err(format!(
                    "TEST() in '{file_path}' must define `parameters` and `cases` together"
                ));
            }
        };
    let raw_parameters = non_empty_mapping(raw_parameters, "parameters", file_path)?;
    let raw_cases = non_empty_mapping(raw_cases, "cases", file_path)?;
    let parameters = raw_parameters
        .iter()
        .map(|(key, declaration)| parameter(key, declaration, file_path))
        .collect::<Parsed<Vec<_>>>()?;
    let cases = raw_cases
        .iter()
        .map(|raw_case| case(raw_case, &parameters, file_path))
        .collect::<Parsed<Vec<_>>>()?;
    Ok((parameters, cases))
}
