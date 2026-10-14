//! The typed confirmation prompt.

use crate::build_command::models::Confirmation;

/// The warning, a blank line, then the prompt for the expected text.
#[must_use]
pub fn render_confirmation_prompt(confirmation: &Confirmation) -> String {
    format!(
        "{}\n\nType `{}` to continue: ",
        confirmation.warning, confirmation.expected
    )
}
