//! Python's cursor intrinsic scan over quotes, comments, identifier boundaries and calls.

use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

use crate::sql_lexing::main::python_non_code_end::python_non_code_end;
use crate::sql_lexing::main::unclosed_construct::unclosed_construct;
use crate::sql_lexing::models::NonCode;

const INTRINSIC_NAMES: [&str; 2] = ["__cursor_start", "__cursor_end"];

/// What Python's scan finds at one offset.
pub(crate) enum ScanStep {
    Next(usize),
    Unclosed(Unclosed),
    /// An intrinsic name at identifier boundaries, ending at `end`.
    Intrinsic {
        name: &'static str,
        end: usize,
    },
    /// Python decides by its Unicode identifier rules.
    Deferred,
}

/// How the text after an intrinsic name reads as Python's empty call.
pub(crate) enum CallScan {
    /// `name()`, with the offset of the closing parenthesis.
    Called(usize),
    NotCalled,
    Arguments,
    UnclosedParenthesis,
    /// Quotes, comments or nested parentheses inside the call, which only Python matches.
    Deferred,
}

/// Python's scan at `index`.
pub(crate) fn step(bytes: &[u8], index: usize) -> ScanStep {
    match python_non_code_end(bytes, index) {
        NonCode::End(end) => return ScanStep::Next(end),
        NonCode::Raises => return ScanStep::Unclosed(unclosed_construct(bytes, index)),
        NonCode::Code => {}
    }
    for name in INTRINSIC_NAMES {
        if bytes[index..].starts_with(name.as_bytes()) {
            let end: usize = index + name.len();
            let before: Option<u8> = index.checked_sub(1).map(|previous| bytes[previous]);
            return match (
                continues_identifier(before),
                continues_identifier(bytes.get(end).copied()),
            ) {
                (Some(false), Some(false)) => ScanStep::Intrinsic { name, end },
                (Some(_), Some(_)) => ScanStep::Next(end),
                _ => ScanStep::Deferred,
            };
        }
    }
    ScanStep::Next(index + 1)
}

/// Python's whitespace skip, `(` check, parenthesis match and argument check after a name.
pub(crate) fn call_scan(sql: &str, name_end: usize) -> CallScan {
    let mut open: usize = name_end;
    while let Some(character) = sql[open..].chars().next() {
        if !is_python_space(character) {
            break;
        }
        open += character.len_utf8();
    }
    let bytes: &[u8] = sql.as_bytes();
    if bytes.get(open) != Some(&b'(') {
        return CallScan::NotCalled;
    }
    let mut index: usize = open + 1;
    while let Some(byte) = bytes.get(index) {
        match byte {
            b')' => {
                return if sql[open + 1..index].chars().all(is_python_space) {
                    CallScan::Called(index)
                } else {
                    CallScan::Arguments
                };
            }
            b'-' if bytes.get(index + 1) == Some(&b'-') => return CallScan::Deferred,
            b'/' if bytes.get(index + 1) == Some(&b'*') => return CallScan::Deferred,
            b'#' | b'\'' | b'"' | b'`' | b'$' | b'(' => return CallScan::Deferred,
            _ => index += 1,
        }
    }
    CallScan::UnclosedParenthesis
}

/// Python's `isalnum() or _`; non-ASCII neighbours defer to Python's Unicode rules.
fn continues_identifier(byte: Option<u8>) -> Option<bool> {
    match byte {
        None => Some(false),
        Some(byte) if !byte.is_ascii() => None,
        Some(byte) => Some(byte.is_ascii_alphanumeric() || byte == b'_'),
    }
}

/// Python's `any(name in sql for name in _INTRINSIC_NAMES)`.
pub(crate) fn contains_intrinsic_name(sql: &str) -> bool {
    INTRINSIC_NAMES.iter().any(|name| sql.contains(name))
}
