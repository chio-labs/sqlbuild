//! Quoted SQL text boundaries under a quoting policy.

use crate::sql_scan::models::{QuotePolicy, Unclosed};

/// Return the index after the quoted text whose opening quote is at `start`.
pub(crate) fn quote_end(sql: &[u8], start: usize, policy: QuotePolicy) -> Result<usize, Unclosed> {
    let quote = sql[start];
    let backslash_escapes = policy.backslash_escapes(quote);
    let mut index = start + 1;
    while index < sql.len() {
        let byte = sql[index];
        if backslash_escapes && byte == b'\\' && index + 1 < sql.len() {
            index += 2;
        } else if byte != quote {
            index += 1;
        } else if sql.get(index + 1) == Some(&quote) {
            index += 2;
        } else {
            return Ok(index + 1);
        }
    }
    Err(Unclosed::Quote)
}
