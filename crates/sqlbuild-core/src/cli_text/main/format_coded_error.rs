//! A result-stored coded error, as CLI expected errors render it.

use crate::cli_text::_helpers::coded_error::coded_error;
use crate::cli_text::models::CliStyle;

/// `format_coded_error`: the coded message, later lines muted, then any help line.
#[must_use]
pub fn format_coded_error(
    (code, message, help): (&str, &str, Option<&str>),
    include_error_label: bool,
    style: CliStyle,
) -> String {
    coded_error((code, message, help), include_error_label, style)
}
