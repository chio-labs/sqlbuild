//! A compact inline diagnostic wrapped to two display lines.

use crate::cli_text::_helpers::coded_error::{
    inline_error_text, style_code_prefix, truncate_lines, wrap_paragraphs,
};
use crate::cli_text::models::CliStyle;

/// The `[code] message` and `= help:` text wrapped to two lines, truncated with an ellipsis.
#[must_use]
pub fn format_inline_error_lines(
    (code, message, help): (Option<&str>, &str, Option<&str>),
    content_width: usize,
    style: CliStyle,
) -> Vec<String> {
    let code_prefix: String = code.map_or_else(String::new, |code| format!("[{code}]"));
    let wrapped: Vec<String> = wrap_paragraphs(
        &inline_error_text(&code_prefix, message, help),
        content_width,
    );
    style_code_prefix(truncate_lines(wrapped, content_width), &code_prefix, style)
}
