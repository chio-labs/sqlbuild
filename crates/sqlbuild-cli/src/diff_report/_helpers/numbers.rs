//! Python's `{:,}` and `{:.2%}` number formats.

/// An integer with comma thousands separators.
pub(crate) fn grouped(value: i64) -> String {
    let digits: String = value.unsigned_abs().to_string();
    let mut result: String = String::new();
    for (index, digit) in digits.chars().enumerate() {
        if index > 0 && (digits.len() - index).is_multiple_of(3) {
            result.push(',');
        }
        result.push(digit);
    }
    if value < 0 {
        format!("-{result}")
    } else {
        result
    }
}

/// A ratio as a percentage with two decimals.
pub(crate) fn percent(ratio: f64) -> String {
    format!("{:.2}%", ratio * 100.0)
}

/// `numerator / denominator` as a percentage, or `0.00%` without a denominator.
pub(crate) fn percentage(numerator: i64, denominator: i64) -> String {
    if denominator == 0 {
        return "0.00%".to_owned();
    }
    percent(numerator as f64 / denominator as f64)
}
