//! Python string and integer semantics the type normalization relies on, for ASCII text.

use crate::type_system::constants::PYTHON_ASCII_WHITESPACE;

/// The result of Python's `int(text)` on one parameter.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum PythonInt {
    Value(i64),
    Invalid,
    /// A valid integer outside `i64`; Python keeps it, so the caller defers.
    TooLarge,
}

pub(crate) fn is_python_space(byte: u8) -> bool {
    PYTHON_ASCII_WHITESPACE.contains(&byte)
}

/// Python's `str.strip()`.
pub(crate) fn python_strip(text: &str) -> &str {
    text.trim_matches(|character: char| character.is_ascii() && is_python_space(character as u8))
}

/// Python's `re.sub(r"\s+", "", text)`.
pub(crate) fn remove_python_space(text: &str) -> String {
    text.chars()
        .filter(|character| !(character.is_ascii() && is_python_space(*character as u8)))
        .collect()
}

/// Python's base-10 `int(text)`: whitespace, a sign, and single underscores between digits.
pub(crate) fn python_int(text: &str) -> PythonInt {
    let stripped: &str = python_strip(text);
    let (negative, digits) = match stripped.as_bytes().first() {
        Some(b'-') => (true, &stripped[1..]),
        Some(b'+') => (false, &stripped[1..]),
        _ => (false, stripped),
    };
    let bytes: &[u8] = digits.as_bytes();
    let valid: bool = !bytes.is_empty()
        && bytes.first().is_some_and(u8::is_ascii_digit)
        && bytes.last().is_some_and(u8::is_ascii_digit)
        && bytes
            .iter()
            .all(|byte| byte.is_ascii_digit() || *byte == b'_')
        && !digits.contains("__");
    if !valid {
        return PythonInt::Invalid;
    }
    let mut value: i64 = 0;
    for byte in bytes.iter().filter(|byte| byte.is_ascii_digit()) {
        let digit: i64 = i64::from(byte - b'0');
        let next: Option<i64> = value.checked_mul(10).and_then(|scaled| {
            if negative {
                scaled.checked_sub(digit)
            } else {
                scaled.checked_add(digit)
            }
        });
        let Some(next) = next else {
            return PythonInt::TooLarge;
        };
        value = next;
    }
    PythonInt::Value(value)
}

/// Python's `_split_type_and_params`; None for a parameter beyond `i64`.
pub(crate) fn split_type_and_params(type_sql: &str) -> Option<(&str, Vec<i64>)> {
    let candidate: &str = type_sql.strip_suffix('\n').unwrap_or(type_sql);
    let name_end: usize = candidate
        .bytes()
        .position(|byte| !(byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_'))
        .unwrap_or(candidate.len());
    if name_end == 0 {
        return Some((type_sql, Vec::new()));
    }
    let (name, rest) = candidate.split_at(name_end);
    if rest.is_empty() {
        return Some((name, Vec::new()));
    }
    let Some(raw_params) = rest
        .strip_prefix('(')
        .and_then(|inner| inner.strip_suffix(')'))
        .filter(|inner| !inner.contains(')'))
    else {
        return Some((type_sql, Vec::new()));
    };
    let mut params: Vec<i64> = Vec::new();
    if raw_params.is_empty() {
        return Some((name, params));
    }
    for raw_part in raw_params.split(',') {
        match python_int(raw_part) {
            PythonInt::Value(value) => params.push(value),
            PythonInt::Invalid => {}
            PythonInt::TooLarge => return None,
        }
    }
    Some((name, params))
}
