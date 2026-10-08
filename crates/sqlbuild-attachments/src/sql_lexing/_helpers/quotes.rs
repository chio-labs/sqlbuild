//! Python's quoted text ends: `'` and `"` double to escape, backticks do not.

use sqlbuild_sqltext::sql_scan::models::QuotePolicy;

/// Only dollar quotes: Python's own quote scan does not double backticks, so quotes run here.
pub(crate) const DOLLAR_POLICY: QuotePolicy = QuotePolicy {
    backtick_identifiers: false,
    single_quote_backslash_escapes: false,
    double_quote_backslash_escapes: false,
    dollar_quotes: true,
};

/// The end of the text quoted at `start`, or None when Python finds it unclosed.
pub(crate) fn quoted_end(bytes: &[u8], start: usize, quote: u8) -> Option<usize> {
    let mut index: usize = start + 1;
    loop {
        index += bytes[index..].iter().position(|byte| *byte == quote)?;
        if quote != b'`' && bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Some(index + 1);
    }
}
