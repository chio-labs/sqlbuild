//! TEST header fields: name, mode, analysis flag and cursor bounds.

use crate::sql_tests::_helpers::mode::defined_modes;
use crate::sql_tests::_helpers::parameters::entry;
use crate::sql_tests::constants::{
    MODE_KEY, MODEL_MODE, NAME_KEY, SQL_ANALYSIS_KEY, SQL_TEST_MODES,
};
use crate::sql_values::models::{RawKey, RawSqlValue};
use sqlbuild_core::text::main::python_strip::python_strip;

pub(crate) fn cursor_bound(
    header: &[(RawKey, RawSqlValue)],
    key: &str,
    file_path: &str,
) -> Result<Option<String>, String> {
    match entry(header, key) {
        None | Some(RawSqlValue::Null) => Ok(None),
        Some(RawSqlValue::Int(number)) => Ok(Some(number.to_string())),
        Some(RawSqlValue::BigInt(digits)) => Ok(Some(digits.clone())),
        Some(RawSqlValue::Str(text)) if !python_strip(text).is_empty() => {
            Ok(Some(python_strip(text).to_owned()))
        }
        Some(_) => Err(format!(
            "TEST() {key} in '{file_path}' must be a non-empty string or an integer"
        )),
    }
}

pub(crate) fn header_checks(
    header: &[(RawKey, RawSqlValue)],
    file_path: &str,
) -> Result<(), String> {
    if let Some(name) = entry(header, NAME_KEY)
        && !matches!(name, RawSqlValue::Str(text) if !python_strip(text).is_empty())
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
