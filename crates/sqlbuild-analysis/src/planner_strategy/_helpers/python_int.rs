//! Python's `int(text)` for batch sizes.

use sqlbuild_core::text::main::decimal_digit_value::decimal_digit_value;

/// Base-10 `int(text)`: surrounding whitespace, a sign, decimal digits and single underscores between them; `None` where Python raises or the value leaves `i128`.
pub(crate) fn python_int(text: &str) -> Option<i128> {
    let trimmed: &str = text.trim();
    let (negative, digits) = match trimmed.chars().next() {
        Some('-') => (true, &trimmed[1..]),
        Some('+') => (false, &trimmed[1..]),
        _ => (false, trimmed),
    };
    let mut value: i128 = 0;
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
        value = value.checked_mul(10)?.checked_add(i128::from(digit))?;
        previous_underscore = false;
    }
    if previous_underscore {
        return None;
    }
    Some(if negative { -value } else { value })
}
