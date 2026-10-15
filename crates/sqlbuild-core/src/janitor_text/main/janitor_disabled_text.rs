//! Guidance when janitor is not enabled for the project.

use crate::cli_text::models::CliStyle;
use crate::constants::PROJECT_CONFIG_FILENAME;
use crate::janitor_text::constants::DISABLED_DETAIL;

/// How to enable janitor and preview cleanup.
#[must_use]
pub fn janitor_disabled_text(style: CliStyle) -> String {
    format!(
        "{}\n\n{}\n\nAdd this block to {}:\n\n[janitor]\nenabled = true\n\n\
         After enabling, run janitor again to preview cleanup:\n  {}\n",
        style.warning_strong("Janitor is disabled for this project."),
        style.warning(DISABLED_DETAIL),
        style.object_name(PROJECT_CONFIG_FILENAME),
        style.accent("sqb janitor")
    )
}
