//! Leading decimal digits of text, without a fallible parse.

use crate::clickhouse::constants::DECIMAL_RADIX;

/// The number the leading ASCII digits of `text` spell; `None` when there are none or it overflows.
pub(crate) fn leading_number(text: &str) -> Option<u64> {
    let mut number: Option<u64> = None;
    for character in text.chars() {
        let Some(digit) = character.to_digit(DECIMAL_RADIX) else {
            break;
        };
        number = number
            .unwrap_or_default()
            .checked_mul(u64::from(DECIMAL_RADIX))?
            .checked_add(u64::from(digit))
            .map(Some)?;
    }
    number
}
