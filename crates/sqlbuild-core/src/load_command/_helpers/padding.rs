//! Python format-spec padding and digit grouping.

/// `f"{text:<width}"`: left-aligned, padded by character count.
pub(crate) fn pad_right(text: &str, width: usize) -> String {
    let length: usize = text.chars().count();
    format!("{text}{}", " ".repeat(width.saturating_sub(length)))
}

/// `f"{value:,}"`: the integer with comma-separated thousands.
pub(crate) fn group_thousands(value: i64) -> String {
    let digits: String = value.unsigned_abs().to_string();
    let mut grouped: String = String::new();
    for (index, digit) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            grouped.push(',');
        }
        grouped.push(digit);
    }
    if value < 0 {
        format!("-{grouped}")
    } else {
        grouped
    }
}
