//! Confirmed clone fingerprint propagation progress.

use crate::cli_text::models::CliStyle;
use crate::clone_text::constants::{FINGERPRINT_LABEL, FINGERPRINT_LABEL_WIDTH};

/// `  fingerprint[ completed/total] propagated OK`.
#[must_use]
pub fn render_clone_fingerprint_progress_line(
    completed: i64,
    total: i64,
    style: CliStyle,
) -> String {
    let width: usize = total.to_string().len();
    format!(
        "  {FINGERPRINT_LABEL:<FINGERPRINT_LABEL_WIDTH$}[{completed:>width$}/{total}] propagated {}",
        style.status("OK")
    )
}
