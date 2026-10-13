//! The parenthesis closing one opened at a Python string offset.

use crate::code_scanner::_helpers::generic::generic_skip_end;
use crate::code_scanner::_helpers::offsets::{byte_offset, char_offset};
use crate::code_scanner::models::CodeScanner;
use crate::sql_scan::main::dialect_matching_paren::dialect_matching_paren;
use crate::sql_scan::models::Unclosed;

/// The code point offset of the parenthesis closing the one at `open`, skipping text and comments.
pub fn scanner_matching_paren(scanner: &CodeScanner, open: usize) -> Result<usize, Unclosed> {
    let sql: &[u8] = scanner.sql.as_bytes();
    let start: usize = byte_offset(scanner, open);
    let close: usize = match &scanner.syntax {
        Some(syntax) => dialect_matching_paren(sql, start, syntax)?,
        None => generic_matching_paren(sql, start)?,
    };
    Ok(char_offset(scanner, close))
}

fn generic_matching_paren(sql: &[u8], open: usize) -> Result<usize, Unclosed> {
    let mut depth: usize = 1;
    let mut index: usize = open + 1;
    while index < sql.len() {
        if let Some(end) = generic_skip_end(sql, index)? {
            index = end;
            continue;
        }
        if sql[index] == b'(' {
            depth += 1;
        } else if sql[index] == b')' {
            depth -= 1;
            if depth == 0 {
                return Ok(index);
            }
        }
        index += 1;
    }
    Err(Unclosed::Parenthesis)
}
