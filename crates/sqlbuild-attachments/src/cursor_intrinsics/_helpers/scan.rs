//! Python's cursor intrinsic scan over quotes, comments and identifier boundaries.

use crate::sql_lexing::main::python_non_code_end::python_non_code_end;
use crate::sql_lexing::models::NonCode;

const INTRINSIC_NAMES: [&[u8]; 2] = [b"__cursor_start", b"__cursor_end"];
/// The next scan offset after `index`, or `Err` where Python finds an intrinsic or raises.
pub(crate) fn step(bytes: &[u8], index: usize) -> Result<usize, ()> {
    match python_non_code_end(bytes, index) {
        NonCode::End(end) => return Ok(end),
        NonCode::Raises => return Err(()),
        NonCode::Code => {}
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
