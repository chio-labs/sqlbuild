//! The end of the comment or quoted text at one Python string offset.

use crate::code_scanner::_helpers::generic::generic_skip_end;
use crate::code_scanner::_helpers::offsets::{byte_offset, char_offset};
use crate::code_scanner::models::CodeScanner;
use crate::sql_scan::main::dialect_non_code_end::dialect_non_code_end;
use crate::sql_scan::models::Unclosed;

/// Where the comment or quoted text at code point `index` ends; a generic lone `$` is one character.
pub fn scanner_non_code_end(
    scanner: &CodeScanner,
    index: usize,
) -> Result<Option<usize>, Unclosed> {
    let sql: &[u8] = scanner.sql.as_bytes();
    let start: usize = byte_offset(scanner, index);
    let end: Option<usize> = match &scanner.syntax {
        Some(syntax) => dialect_non_code_end(sql, start, syntax)?,
        None => generic_skip_end(sql, start)?,
    };
    Ok(end.map(|end| char_offset(scanner, end)))
}
