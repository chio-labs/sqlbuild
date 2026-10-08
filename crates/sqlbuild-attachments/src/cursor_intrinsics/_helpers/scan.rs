//! Python's cursor intrinsic scan over quotes, comments and identifier boundaries.

use sqlbuild_sqltext::sql_scan::main::comment_end::comment_end;
use sqlbuild_sqltext::sql_scan::main::non_code_end::non_code_end;
use sqlbuild_sqltext::sql_scan::models::QuotePolicy;

const INTRINSIC_NAMES: [&[u8]; 2] = [b"__cursor_start", b"__cursor_end"];
/// Only dollar quotes: Python's own quote scan does not double backticks, so quotes run here.
const DOLLAR_POLICY: QuotePolicy = QuotePolicy {
    backtick_identifiers: false,
    single_quote_backslash_escapes: false,
    double_quote_backslash_escapes: false,
    dollar_quotes: true,
};

/// The next scan offset after `index`, or `Err` where Python finds an intrinsic or raises.
pub(crate) fn step(bytes: &[u8], index: usize) -> Result<usize, ()> {
    if let Some(end) = comment_end(bytes, index).map_err(|_| ())? {
        return Ok(end);
    }
    match bytes[index] {
        quote @ (b'\'' | b'"' | b'`') => return quoted_end(bytes, index, quote),
        b'$' => {
            return Ok(non_code_end(bytes, index, DOLLAR_POLICY)
                .map_err(|_| ())?
                .unwrap_or(index + 1));
        }
        _ => {}
    }
    for name in INTRINSIC_NAMES {
        if bytes[index..].starts_with(name) {
            let end: usize = index + name.len();
            let before: Option<u8> = index.checked_sub(1).map(|previous| bytes[previous]);
            if !continues_identifier(before)? && !continues_identifier(bytes.get(end).copied())? {
                return Err(());
            }
            return Ok(end);
        }
    }
    Ok(index + 1)
}

/// Python's quoted text end: `'` and `"` double to escape, backticks do not.
fn quoted_end(bytes: &[u8], start: usize, quote: u8) -> Result<usize, ()> {
    let mut index: usize = start + 1;
    loop {
        index += bytes[index..]
            .iter()
            .position(|byte| *byte == quote)
            .ok_or(())?;
        if quote != b'`' && bytes.get(index + 1) == Some(&quote) {
            index += 2;
            continue;
        }
        return Ok(index + 1);
    }
}

/// Python's `isalnum() or _`; non-ASCII neighbours defer to Python's Unicode rules.
fn continues_identifier(byte: Option<u8>) -> Result<bool, ()> {
    match byte {
        None => Ok(false),
        Some(byte) if !byte.is_ascii() => Err(()),
        Some(byte) => Ok(byte.is_ascii_alphanumeric() || byte == b'_'),
    }
}

/// Python's `any(name in sql for name in _INTRINSIC_NAMES)`.
pub(crate) fn contains_intrinsic_name(bytes: &[u8]) -> bool {
    for name in INTRINSIC_NAMES {
        if bytes.windows(name.len()).any(|window| window == name) {
            return true;
        }
    }
    false
}
