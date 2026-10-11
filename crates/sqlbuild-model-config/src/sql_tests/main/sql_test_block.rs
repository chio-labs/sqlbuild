//! Python's `build_sql_test_block`: validate one TEST block's header against its SQL.

use crate::sql_tests::_helpers::header::{cursor_bound, header_checks, test_mode};
use crate::sql_tests::_helpers::parameters::{entry, parameters_and_cases};
use crate::sql_tests::constants::{CURSOR_END_KEY, CURSOR_START_KEY, MODEL_MODE, NAME_KEY};
use crate::sql_tests::models::SqlTestBlock;
use crate::sql_values::models::{RawKey, RawSqlValue};

/// The validated fields of one TEST block, or the `SqlTestParseError` message rejecting it.
pub fn sql_test_block(
    header: &[(RawKey, RawSqlValue)],
    sql_body: &str,
    file_path: &str,
) -> Result<SqlTestBlock, String> {
    header_checks(header, file_path)?;
    if sql_body.is_empty() {
        return Err(format!(
            "SQL test '{file_path}' must define SQL after TEST(...)"
        ));
    }
    let name = match entry(header, NAME_KEY) {
        Some(RawSqlValue::Str(text)) => Some(text.clone()),
        _ => None,
    };
    let mode = test_mode(header, sql_body, file_path)?;
    let (parameters, cases) = parameters_and_cases(header, file_path)?;
    let cursor_start = cursor_bound(header, CURSOR_START_KEY, file_path)?;
    let cursor_end = cursor_bound(header, CURSOR_END_KEY, file_path)?;
    if (cursor_start.is_some() || cursor_end.is_some()) && mode != MODEL_MODE {
        return Err(format!(
            "TEST() in '{file_path}' declares `cursor_start` or `cursor_end`, which are only \
             supported for model tests, not mode '{mode}'"
        ));
    }
    Ok(SqlTestBlock {
        name,
        mode,
        parameters,
        cases,
        cursor_start,
        cursor_end,
    })
}
