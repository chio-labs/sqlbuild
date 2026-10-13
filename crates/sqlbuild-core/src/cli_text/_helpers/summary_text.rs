//! Summary footers, completion lines and small aligned text pieces.

use crate::cli_text::constants::{
    COUNT_HEADER_CLOSING, COUNT_HEADER_OPENING, FOOTER_ERROR_LABELS, FOOTER_SKIP_LABELS,
    FOOTER_SUCCESS_LABELS, FOOTER_WARNING_LABELS, PHASE_FAIL_GLYPH, PHASE_OK_GLYPH,
};
use crate::cli_text::models::{AlignedRow, CliStyle, CompletionState, SummaryCount};

fn footer_value(style: CliStyle, count: &SummaryCount) -> String {
    let normalized: String = count.label.to_uppercase();
    let value: String = count.value.to_string();
    let label: &str = normalized.as_str();
    if FOOTER_SUCCESS_LABELS.contains(&label) {
        return style.success(&value);
    }
    if FOOTER_WARNING_LABELS.contains(&label) {
        return style.warning(&value);
    }
    if FOOTER_ERROR_LABELS.contains(&label) {
        return style.error(&value);
    }
    if FOOTER_SKIP_LABELS.contains(&label) {
        return style.muted(&value);
    }
    style.value(&value)
}

/// `format_summary_footer`: `LABEL=value` pairs coloured by outcome, then the elapsed time.
pub(crate) fn summary_footer(
    style: CliStyle,
    counts: &[SummaryCount],
    elapsed: Option<&str>,
) -> String {
    let parts: Vec<String> = counts
        .iter()
        .map(|count| {
            format!(
                "{}{}",
                style.label(&format!("{}=", count.label)),
                footer_value(style, count)
            )
        })
        .collect();
    let rendered: String = parts.join("  ");
    match elapsed {
        Some(elapsed) => format!("{rendered}  {}", style.muted(&format!("({elapsed})"))),
        None => rendered,
    }
}

/// `format_count_noun`: the count with the singular noun for one, else the plural.
pub(crate) fn count_noun(count: i64, singular: &str, plural: Option<&str>) -> String {
    if count == 1 {
        return format!("{count} {singular}");
    }
    match plural.filter(|plural| !plural.is_empty()) {
        Some(plural) => format!("{count} {plural}"),
        None => format!("{count} {singular}s"),
    }
}

/// `format_completion_line`: the state glyph, the label and the trailing summary.
pub(crate) fn completion_line(
    style: CliStyle,
    state: CompletionState,
    label: &str,
    summary: Option<&str>,
) -> String {
    let (glyph, label): (String, String) = match state {
        CompletionState::Fail => (style.error(PHASE_FAIL_GLYPH), style.error_strong(label)),
        CompletionState::Warn => (style.warning(PHASE_OK_GLYPH), style.warning_strong(label)),
        CompletionState::Ok => (style.success(PHASE_OK_GLYPH), label.to_owned()),
    };
    match summary.filter(|summary| !summary.is_empty()) {
        Some(summary) => format!("{glyph} {label}  {summary}"),
        None => format!("{glyph} {label}"),
    }
}

/// `format_aligned_name_value`: the row padded on the plain name's width.
pub(crate) fn aligned_row(row: &AlignedRow) -> String {
    let padding: String = " ".repeat(
        row.name_column_width
            .saturating_sub(row.plain_name.chars().count()),
    );
    format!("{}{}{padding} {}", row.prefix, row.styled_name, row.value)
}

/// The title and count of a `Title (count)` header, when it has that shape.
pub(crate) fn count_header_parts(text: &str) -> Option<(&str, &str)> {
    if !text.ends_with(COUNT_HEADER_CLOSING) {
        return None;
    }
    let position: usize = text.rfind(COUNT_HEADER_OPENING)?;
    Some((
        &text[..position],
        &text[position + COUNT_HEADER_OPENING.len()..],
    ))
}

/// `resolve_name_column_width`: the longest name, at least `min_width`.
pub(crate) fn name_column_width(names: &[String], min_width: usize) -> usize {
    names
        .iter()
        .map(|name| name.chars().count())
        .fold(min_width, usize::max)
}

/// The overflow hint of a truncated section, when entries are hidden.
pub(crate) fn overflow_line(hidden: i64, indent: &str, flag: &str) -> Option<String> {
    (hidden > 0).then(|| {
        CliStyle { use_color: true }.muted(&format!(
            "{indent}... and {hidden} more (use {flag} to show all)"
        ))
    })
}
