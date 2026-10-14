//! The scale of a decimal type written as `DECIMAL`, `NUMERIC` or `NUMBER`.

use crate::planner_strategy::constants::DECIMAL_TYPE_NAMES;

/// Digits after optional spaces, then optional spaces: the rest of the text.
fn digits_then_spaces(text: &str) -> Option<(&str, &str)> {
    let text: &str = text.trim_start_matches(char::is_whitespace);
    let end: usize = text
        .find(|character: char| !character.is_ascii_digit())
        .unwrap_or(text.len());
    if end == 0 {
        return None;
    }
    Some((
        &text[..end],
        text[end..].trim_start_matches(char::is_whitespace),
    ))
}

/// Whether a full `DECIMAL[(p[, s])]` match has scale zero (absent counts as zero); `None` when the text does not match.
pub(crate) fn decimal_scale_is_zero(normalized: &str) -> Option<bool> {
    let rest: &str = DECIMAL_TYPE_NAMES
        .iter()
        .find_map(|name| normalized.strip_prefix(name))?;
    if rest.is_empty() {
        return Some(true);
    }
    let inner: &str = rest.strip_prefix('(')?.strip_suffix(')')?;
    let (_, after_precision) = digits_then_spaces(inner)?;
    if after_precision.is_empty() {
        return Some(true);
    }
    let (scale, tail) = digits_then_spaces(after_precision.strip_prefix(',')?)?;
    tail.is_empty()
        .then(|| scale.chars().all(|digit| digit == '0'))
}
