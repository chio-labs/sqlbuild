//! `parse_integer_text`: the fast path of integer cursor text.

/// The value of `text` when it is a plain ASCII signed integer that fits `i128`.
#[must_use]
pub fn parse_integer_text(text: &str) -> Option<i128> {
    let digits: &str = text.strip_prefix(['+', '-']).unwrap_or(text);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let Ok(value) = text.parse::<i128>() else {
        return None;
    };
    Some(value)
}
