//! TEST header fields: name, mode, analysis flag and cursor bounds.

use crate::execution_limits::constants::TIMEOUT_KEY;
use crate::execution_limits::main::parse_execution_limit::parse_execution_limit;
use crate::sql_tests::_helpers::mode::defined_modes;
use crate::sql_tests::_helpers::parameters::entry;
use crate::sql_tests::constants::{
    MODE_KEY, MODEL_MODE, NAME_KEY, SQL_ANALYSIS_KEY, SQL_TEST_MODES,
};
use crate::sql_values::models::{RawKey, RawSqlValue};

pub(crate) fn cursor_bound(
    header: &[(RawKey, RawSqlValue)],
    key: &str,
    file_path: &str,
) -> Result<Option<String>, String> {
    match entry(header, key) {
        None | Some(RawSqlValue::Null) => Ok(None),
        Some(RawSqlValue::Int(number)) => Ok(Some(number.to_string())),
        Some(RawSqlValue::BigInt(digits)) => Ok(Some(digits.clone())),
        Some(RawSqlValue::Str(text)) if !str::trim(text).is_empty() => {
            Ok(Some(str::trim(text).to_owned()))
        }
        Some(_) => Err(format!(
            "TEST() {key} in '{file_path}' must be a non-empty string or an integer"
        )),
    }
}

/// A header's validated `timeout`: a positive fixed duration or `disabled`.
pub(crate) fn header_timeout(
    header: &[(RawKey, RawSqlValue)],
    header_name: &str,
    file_path: &str,
) -> Result<Option<String>, String> {
    match entry(header, TIMEOUT_KEY) {
        None | Some(RawSqlValue::Null) => Ok(None),
        Some(RawSqlValue::Str(text)) if parse_execution_limit(text).is_some() => {
            Ok(Some(text.trim().to_owned()))
        }
        Some(_) => Err(format!(
            "{header_name} timeout in '{file_path}' must be a positive fixed duration such as \
             \"45s\" or \"2m\", or \"disabled\""
        )),
    }
}

pub(crate) fn header_checks(
    header: &[(RawKey, RawSqlValue)],
    file_path: &str,
) -> Result<(), String> {
    if let Some(name) = entry(header, NAME_KEY)
        && !matches!(name, RawSqlValue::Str(text) if !str::trim(text).is_empty())
    {
        return Err(format!(
            "TEST() name in '{file_path}' must be a non-empty string"
        ));
    }
    match entry(header, MODE_KEY) {
        None | Some(RawSqlValue::Str(_)) => {}
        Some(_) => return Err(format!("TEST() mode in '{file_path}' must be a string")),
    }
    if let Some(RawSqlValue::Str(mode)) = entry(header, MODE_KEY)
        && !SQL_TEST_MODES.contains(&mode.as_str())
    {
        return Err(format!(
            "TEST() mode in '{file_path}' must be one of: {}",
            SQL_TEST_MODES.join(", ")
        ));
    }
    if entry(header, SQL_ANALYSIS_KEY).is_some_and(|value| !matches!(value, RawSqlValue::Bool(_))) {
        return Err(format!(
            "TEST() sql_analysis in '{file_path}' must be a boolean"
        ));
    }
    Ok(())
}

pub(crate) fn test_mode(
    header: &[(RawKey, RawSqlValue)],
    sql_body: &str,
    file_path: &str,
) -> Result<&'static str, String> {
    if let Some(RawSqlValue::Str(mode)) = entry(header, MODE_KEY) {
        return Ok(SQL_TEST_MODES
            .iter()
            .find(|known| **known == mode)
            .copied()
            .unwrap_or(MODEL_MODE));
    }
    let modes = defined_modes(sql_body);
    if modes.len() > 1 {
        return Err(format!(
            "SQL test '{file_path}' defines actual CTEs for several test modes ({}); each TEST \
             block tests one kind of logic",
            modes.join(", ")
        ));
    }
    Ok(modes[0])
}
