//! Python's `assert_no_unresolved_sql_markers`: the first reference call left in executable SQL.

use crate::reference_markers::constants::REFERENCE_CALL_PREFIXES;
use crate::sql_lexing::main::python_non_code_end::python_non_code_end;
use crate::sql_lexing::main::unclosed_construct::unclosed_construct;
use crate::sql_lexing::models::NonCode;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

fn marker_in_code(bytes: &[u8], prefix: &[u8]) -> Result<bool, Unclosed> {
    if !bytes.windows(prefix.len()).any(|window| window == prefix) {
        return Ok(false);
    }
    let mut index: usize = 0;
    while index < bytes.len() {
        match python_non_code_end(bytes, index) {
            NonCode::End(end) => index = end,
            NonCode::Raises => return Err(unclosed_construct(bytes, index)),
            NonCode::Code if bytes[index..].starts_with(prefix) => return Ok(true),
            NonCode::Code => index += 1,
        }
    }
    Ok(false)
}

/// The index of the first reference kind still called in code, or the construct left unclosed.
pub fn unresolved_reference_marker(sql: &str) -> Result<Option<usize>, Unclosed> {
    for (position, prefix) in REFERENCE_CALL_PREFIXES.iter().enumerate() {
        if marker_in_code(sql.as_bytes(), prefix)? {
            return Ok(Some(position));
        }
    }
    Ok(None)
}
