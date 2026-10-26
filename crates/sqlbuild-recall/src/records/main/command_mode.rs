//! `command_mode`: what a diagnostic command checked, named from its flags.

use crate::records::constants::{CONFIG_AND_CONNECTION_MODE, CONFIG_ONLY_MODE, DEBUG_COMMAND};

/// The mode of `sqb debug`, from whether `--no-connection` was given; `None` for other commands.
#[must_use]
pub fn command_mode(command: Option<&str>, no_connection: bool) -> Option<&'static str> {
    (command == Some(DEBUG_COMMAND)).then_some(if no_connection {
        CONFIG_ONLY_MODE
    } else {
        CONFIG_AND_CONNECTION_MODE
    })
}
