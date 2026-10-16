//! The display form of an ingestr command line.

use crate::shell_text::main::shell_quote::shell_quote;

/// The arguments shell-quoted and joined with spaces, like Python's `shlex.join`.
#[must_use]
pub fn format_ingestr_command(arguments: &[String]) -> String {
    arguments
        .iter()
        .map(|argument| shell_quote(argument))
        .collect::<Vec<String>>()
        .join(" ")
}
