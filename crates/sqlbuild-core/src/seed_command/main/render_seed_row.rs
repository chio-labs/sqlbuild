//! The progress row of one finished seed.

use crate::cli_text::main::format_coded_error::format_coded_error;
use crate::cli_text::models::CliStyle;
use crate::seed_command::constants::{FAIL_STATUS, OK_STATUS, SEED_NAME_WIDTH, STATUS_WIDTH};
use crate::seed_command::models::SeedRow;

/// `  <i>/<n>  seed      <name> <STATUS> <duration>`, then its error line when there is one.
#[must_use]
pub fn render_seed_row(row: &SeedRow, style: CliStyle) -> String {
    let status: String = style.status(if row.succeeded {
        OK_STATUS
    } else {
        FAIL_STATUS
    });
    let duration: String = row
        .duration_ms
        .map(|milliseconds| format!("{:.2}s", milliseconds / 1000.0))
        .unwrap_or_default();
    let mut text: String = format!(
        "  {}/{}  seed      {:<SEED_NAME_WIDTH$} {status:<STATUS_WIDTH$} {duration}\n",
        row.ordinal, row.total, row.name
    );
    if let Some(message) = &row.error_message {
        let rendered: String = match &row.error_code {
            Some(code) => {
                format_coded_error((code, message, row.error_help.as_deref()), true, style)
            }
            None => message.clone(),
        };
        text.push_str(&format!("    {rendered}\n"));
    }
    text
}
