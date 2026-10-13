//! Bounded, difference-aware rendering of example values and keys.

use sqlbuild_cache::digest::main::sha256_hex::sha256_hex;

use crate::diff_report::_helpers::numbers::grouped;
use crate::diff_report::constants::MAX_RENDERED_KEY_LENGTH;
use crate::diff_report::models::{DiffExampleOptions, RenderedValue};

fn first_difference(left: &[char], right: &[char]) -> Option<usize> {
    if let Some(index) = left.iter().zip(right).position(|(a, b)| a != b) {
        return Some(index);
    }
    (left.len() != right.len()).then(|| left.len().min(right.len()))
}

fn render_value(
    text: &[char],
    first_difference: Option<usize>,
    options: DiffExampleOptions,
) -> RenderedValue {
    let original_length: usize = text.len();
    let full: String = text.iter().collect();
    if options.suppress_values {
        return RenderedValue {
            text: None,
            original_length,
            truncated: false,
            suppressed: true,
            first_difference,
        };
    }
    let Some(limit) = options
        .max_value_length
        .filter(|limit| original_length > *limit)
    else {
        return RenderedValue {
            text: Some(full),
            original_length,
            truncated: false,
            suppressed: false,
            first_difference,
        };
    };
    let difference: usize = first_difference.unwrap_or(0);
    let context_before: usize = (limit / 3).min(limit.saturating_sub(1));
    let start: usize = difference
        .saturating_sub(context_before)
        .min(original_length - limit);
    let end: usize = start + limit;
    let fragment: String = text[start..end].iter().collect();
    RenderedValue {
        text: Some(format!(
            "{}{fragment}{}",
            if start > 0 { "…" } else { "" },
            if end < original_length { "…" } else { "" }
        )),
        original_length,
        truncated: true,
        suppressed: false,
        first_difference,
    }
}

/// Two unequal values rendered around their first differing character.
pub(crate) fn render_example_pair(
    left: &str,
    right: &str,
    options: DiffExampleOptions,
) -> (RenderedValue, RenderedValue) {
    let left: Vec<char> = left.chars().collect();
    let right: Vec<char> = right.chars().collect();
    let difference: Option<usize> = first_difference(&left, &right);
    (
        render_value(&left, difference, options),
        render_value(&right, difference, options),
    )
}

/// One bounded value for terminal output.
pub(crate) fn display_example_value(value: &RenderedValue) -> String {
    if value.suppressed {
        return format!(
            "<value suppressed; {} chars>",
            grouped(value.original_length as i64)
        );
    }
    let rendered: &str = value.text.as_deref().unwrap_or_default();
    if value.truncated {
        return format!(
            "{rendered} [truncated; {} chars]",
            grouped(value.original_length as i64)
        );
    }
    rendered.to_owned()
}

/// Ordinary keys complete; exceptionally long keys shortened and identified by digest.
pub(crate) fn render_key_value(text: &str) -> String {
    let length: usize = text.chars().count();
    if length <= MAX_RENDERED_KEY_LENGTH {
        return text.to_owned();
    }
    let digest: String = sha256_hex(text.as_bytes());
    let prefix: String = text.chars().take(MAX_RENDERED_KEY_LENGTH).collect();
    format!(
        "{prefix}… [truncated; {} chars; sha256:{}]",
        grouped(length as i64),
        &digest[..12]
    )
}
