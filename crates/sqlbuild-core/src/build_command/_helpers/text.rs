//! Safe display of resolved context values.

use crate::build_command::constants::{
    C0_CONTROL_CODE_LIMIT, C1_CONTROL_CODE_LIMIT, C1_CONTROL_CODE_START, NOT_SET,
};

/// Escape C0 and C1 control characters as `\xNN`.
pub(crate) fn sanitize(value: &str) -> String {
    let mut text: String = String::with_capacity(value.len());
    for character in value.chars() {
        let code: u32 = u32::from(character);
        if code < C0_CONTROL_CODE_LIMIT
            || (C1_CONTROL_CODE_START..C1_CONTROL_CODE_LIMIT).contains(&code)
        {
            text.push_str(&format!("\\x{code:02x}"));
        } else {
            text.push(character);
        }
    }
    text
}

/// The sanitized value, or `not set`.
pub(crate) fn display_value(value: Option<&str>) -> String {
    value.map_or_else(|| NOT_SET.to_owned(), sanitize)
}

/// A count with `,` thousands separators.
pub(crate) fn grouped(value: usize) -> String {
    let digits: String = value.to_string();
    let mut text: String = String::with_capacity(digits.len() + digits.len() / 3);
    for (index, digit) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            text.push(',');
        }
        text.push(digit);
    }
    text
}
