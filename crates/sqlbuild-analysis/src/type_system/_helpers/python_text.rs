//! Python string and integer semantics the type normalization relies on.

use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

use crate::type_system::models::PythonInteger;

/// Python's `text.upper()` under the running Python's Unicode version.
pub(crate) fn upper(text: &str) -> String {
    str::to_uppercase(text)
}

/// Python's `re.sub(r"\s+", "", text)`.
pub(crate) fn remove_python_space(text: &str) -> String {
    text.chars()
        .filter(|character| !char::is_whitespace(*character))
        .collect()
}

/// Python's base-10 `int(text)`, None where Python raises `ValueError`.
pub(crate) fn python_int(text: &str) -> Option<PythonInteger> {
    let stripped: &str = str::trim(text);
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
        let digit: u32 = decimal_digit_value(character)?;
        value.push(char::from_digit(digit, 10)?);
        previous_underscore = false;
    }
    if value.is_empty() || previous_underscore {
        return None;
    }
    Some(PythonInteger::from_digits(negative, &value))
}

/// Python's `_split_type_and_params`.
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
