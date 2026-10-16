//! Lowercase ASCII identifiers: `re.fullmatch(r"^[a-z][a-z0-9_]*$", value)`.

/// Whether `value` is a lowercase ASCII letter followed by lowercase letters, digits or `_`.
#[must_use]
pub fn is_lowercase_identifier(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && bytes.all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
}
