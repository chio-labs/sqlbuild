//! The header announcing the selected audits.

use crate::cli_text::models::CliStyle;

/// A blank line, `Audit (<n> selected, <m> models)`, and a blank line.
#[must_use]
pub fn render_audit_header((audits, models): (usize, usize), style: CliStyle) -> String {
    format!(
        "\n{}\n\n",
        style.success_strong(&format!("Audit ({audits} selected, {models} models)"))
    )
}
