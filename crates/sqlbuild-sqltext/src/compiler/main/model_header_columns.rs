//! The `columns (...)` body of a MODEL header and the span of each column entry.

use crate::compiler::_helpers::model_headers::columns::{columns_open, scan_columns};
use crate::compiler::_helpers::model_headers::matching::match_one;
use crate::compiler::_helpers::model_headers::tokenization::{HeaderToken, tokenize_one};
use crate::compiler::models::HeaderColumns;

/// Python's `model_header_columns_span`: code-point offsets of the columns body and entries.
pub fn model_header_columns(contents: &str) -> Result<Option<HeaderColumns>, String> {
    let Some((header_start, header_end, _)) = match_one(contents) else {
        return Ok(None);
    };
    let header: String = contents
        .chars()
        .skip(header_start)
        .take(header_end - header_start)
        .collect();
    let tokens: Vec<HeaderToken> = tokenize_one(&header)?;
    match columns_open(&tokens) {
        Some(open) => scan_columns(&tokens, open, header_start),
        None => Ok(None),
    }
}
