//! Python string and integer semantics the type normalization relies on.

use sqlbuild_core::text::main::active_python_text::active_python_text;
use sqlbuild_core::text::main::is_python_space::is_python_space;
use sqlbuild_core::text::main::python_decimal_value::python_decimal_value;
use sqlbuild_core::text::main::python_strip::python_strip;
use sqlbuild_core::text::main::python_upper::python_upper;
use sqlbuild_core::text::models::PythonText;

use crate::type_system::models::PythonInteger;

/// Python's `text.upper()` under the running Python's Unicode version.
pub(crate) fn upper(text: &str) -> String {
    python_upper(active_python_text(), text)
}

/// Python's `re.sub(r"\s+", "", text)`.
pub(crate) fn remove_python_space(text: &str) -> String {
    text.chars()
        .filter(|character| !is_python_space(*character))
        .collect()
}

/// Python's base-10 `int(text)`: whitespace, a sign, Unicode decimal digits and single
/// underscores between digits; None where Python raises `ValueError`.
pub(crate) fn python_int(text: &str) -> Option<PythonInteger> {
    let python: PythonText = active_python_text();
    let stripped: &str = python_strip(text);
    let (negative, digits) = match stripped.chars().next() {
        Some('-') => (true, &stripped[1..]),
        Some('+') => (false, &stripped[1..]),
        _ => (false, stripped),
    };
    let mut value: String = String::with_capacity(digits.len() + 1);
    let mut previous_underscore: bool = true;
    for character in digits.chars() {
        if character == '_' {
            if previous_underscore {
                return None;
            }
            previous_underscore = true;
            continue;
        }
        let digit: u32 = python_decimal_value(python, character)?;
        value.push(char::from_digit(digit, 10)?);
        previous_underscore = false;
    }
    if value.is_empty() || previous_underscore {
        return None;
    }
    Some(PythonInteger::from_digits(negative, &value))
}

/// Python's `_split_type_and_params`: the regex `^([A-Z0-9_]+)(?:\(([^)]*)\))?$`, then
/// `int(part.strip())` for each comma-separated parameter, skipping what `int` rejects.
pub(crate) fn split_type_and_params(type_sql: &str) -> (&str, Vec<PythonInteger>) {
    let candidate: &str = type_sql.strip_suffix('\n').unwrap_or(type_sql);
    let name_end: usize = candidate
        .bytes()
        .position(|byte| !(byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_'))
        .unwrap_or(candidate.len());
    if name_end == 0 {
        return (type_sql, Vec::new());
    }
    let (name, rest) = candidate.split_at(name_end);
    if rest.is_empty() {
        return (name, Vec::new());
    }
    let Some(raw_params) = rest
        .strip_prefix('(')
        .and_then(|inner| inner.strip_suffix(')'))
        .filter(|inner| !inner.contains(')'))
    else {
        return (type_sql, Vec::new());
    };
    if raw_params.is_empty() {
        return (name, Vec::new());
    }
    let params: Vec<PythonInteger> = raw_params.split(',').filter_map(python_int).collect();
    (name, params)
}
