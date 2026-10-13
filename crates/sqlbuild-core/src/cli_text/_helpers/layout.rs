//! The shared layout pieces of human CLI output, as `sqlbuild.presentation` renders them.

use crate::cli_text::constants::{
    ELLIPSIS, PHASE_FAIL_GLYPH, PHASE_OK_GLYPH, TREE_BRANCH_GLYPH, TREE_LAST_GLYPH,
};
use crate::cli_text::models::CliStyle;

/// `format_surface_header`: accent title plus dim context.
pub(crate) fn surface_header(style: CliStyle, title: &str, context: &str) -> String {
    let rendered: String = style.title(title);
    if context.is_empty() {
        return rendered;
    }
    format!("{rendered}  {}", style.muted(context))
}

/// `format_phase_line`: state glyph, label, dim summary.
pub(crate) fn phase_line(style: CliStyle, ok: bool, label: &str, summary: &str) -> String {
    let glyph: String = if ok {
        style.success(PHASE_OK_GLYPH)
    } else {
        style.error(PHASE_FAIL_GLYPH)
    };
    let rendered_label: String = if ok {
        label.to_owned()
    } else {
        style.error_strong(label)
    };
    let rendered: String = format!("{glyph} {rendered_label}");
    if summary.is_empty() {
        return rendered;
    }
    format!("{rendered}  {}", style.muted(summary))
}

/// `format_status_cell`: the styled status padded on its plain text to `width`.
pub(crate) fn status_cell(style: CliStyle, status: &str, width: usize) -> String {
    let padding: String = " ".repeat(width.saturating_sub(status.chars().count()));
    format!("{}{padding}", style.status(status))
}

/// `tree_connector`: a dim branch, or the last branch of a group.
pub(crate) fn tree_connector(style: CliStyle, last: bool) -> String {
    style.muted(if last {
        TREE_LAST_GLYPH
    } else {
        TREE_BRANCH_GLYPH
    })
}

/// `"{count} {singular}"`, pluralized with `s` unless the count is one.
pub(crate) fn count_label(count: usize, singular: &str) -> String {
    if count == 1 {
        return format!("{count} {singular}");
    }
    format!("{count} {singular}s")
}

/// The text cut to `width` characters with `...`, or left-justified to `width`.
pub(crate) fn fit(text: &str, width: usize) -> String {
    let length: usize = text.chars().count();
    if length > width {
        if width <= ELLIPSIS.len() {
            return ".".repeat(width);
        }
        let kept: String = text.chars().take(width - ELLIPSIS.len()).collect();
        return format!("{kept}{ELLIPSIS}");
    }
    format!("{text}{}", " ".repeat(width - length))
}
