//! The cursor intrinsic scan over quotes, comments, identifier boundaries and calls.

use sqlbuild_core::text::main::is_python_alnum::is_python_alnum;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::models::PythonText;
use sqlbuild_sqltext::sql_scan::models::Unclosed;

use crate::sql_lexing::main::python_non_code_end::python_non_code_end;
use crate::sql_lexing::main::unclosed_construct::unclosed_construct;
use crate::sql_lexing::models::NonCode;

const INTRINSIC_NAMES: [&str; 2] = ["__cursor_start", "__cursor_end"];

/// What the scan finds at one offset.
pub(crate) enum ScanStep {
    Next(usize),
    Unclosed(Unclosed),
    /// An intrinsic name at identifier boundaries, ending at `end`.
    Intrinsic {
        name: &'static str,
        end: usize,
    },
}

/// How the text after an intrinsic name reads as an empty call.
pub(crate) enum CallScan {
    /// `name()`, with the offset of the closing parenthesis.
    Called(usize),
    NotCalled,
    Arguments,
    /// The call reaches the end of the SQL inside this construct.
    Unclosed(Unclosed),
}

/// The scan at `index`, a character boundary of `sql`.
pub(crate) fn step(python: PythonText, sql: &str, index: usize) -> ScanStep {
    let bytes: &[u8] = sql.as_bytes();
    match python_non_code_end(bytes, index) {
        NonCode::End(end) => return ScanStep::Next(end),
        NonCode::Raises => return ScanStep::Unclosed(unclosed_construct(bytes, index)),
        NonCode::Code => {}
    }
    for name in INTRINSIC_NAMES {
        if bytes[index..].starts_with(name.as_bytes()) {
            let end: usize = index + name.len();
            let bounded: bool = !continues_identifier(python, sql[..index].chars().next_back())
                && !continues_identifier(python, sql[end..].chars().next());
            return if bounded {
                ScanStep::Intrinsic { name, end }
            } else {
                ScanStep::Next(end)
            };
        }
    }
    ScanStep::Next(index + sql[index..].chars().next().map_or(1, char::len_utf8))
}

/// The whitespace skip, `(` check, parenthesis match and argument check after a name.
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
    let mut depth: usize = 1;
    let mut index: usize = open + 1;
    while index < bytes.len() {
        match python_non_code_end(bytes, index) {
            NonCode::End(end) => {
                index = end;
                continue;
            }
            NonCode::Raises => return CallScan::Unclosed(unclosed_construct(bytes, index)),
            NonCode::Code => {}
        }
        match bytes[index] {
            b'(' => depth += 1,
            b')' => {
                depth -= 1;
                if depth == 0 {
                    return if sql[open + 1..index].chars().all(is_python_space) {
                        CallScan::Called(index)
                    } else {
                        CallScan::Arguments
                    };
                }
            }
            _ => {}
        }
        index += 1;
    }
    CallScan::Unclosed(Unclosed::Parenthesis)
}

/// Python's `isalnum() or _` for a neighbouring character; the SQL edge continues nothing.
fn continues_identifier(python: PythonText, character: Option<char>) -> bool {
    character.is_some_and(|character| character == '_' || is_python_alnum(python, character))
}

/// Python's `any(name in sql for name in _INTRINSIC_NAMES)`.
pub(crate) fn contains_intrinsic_name(sql: &str) -> bool {
    INTRINSIC_NAMES.iter().any(|name| sql.contains(name))
}
