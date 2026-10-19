//! Serve one invocation without Python when its parse and project facts allow it.

use std::ffi::OsString;
use std::path::Path;

use crate::argv::main::parse_cli_arguments::parse_cli_arguments;
use crate::argv::models::{ArgvOutcome, ArgvSettings, Namespace};
use crate::native_commands::_helpers::argv_host::{NativeArgvHost, namespace_defaults};
use crate::native_commands::_helpers::decision::native_invocation;
use crate::native_commands::_helpers::execution::run_command;
use crate::native_commands::_helpers::terminal::{
    stdout_supports_color, terminal_columns, write_text,
};
use crate::native_commands::constants::NO_COLOR_OPTION;
use crate::native_commands::errors::PythonNeeded;
use crate::native_commands::models::NativeInvocation;

/// The exit status of an invocation `sqb` served, or why the same arguments go to Python.
pub fn run_native_invocation(
    arguments: &[OsString],
    python_cli: &Path,
) -> Result<i32, PythonNeeded> {
    let arguments: Vec<String> = arguments
        .iter()
        .map(|argument| argument.to_str().map(str::to_owned))
        .collect::<Option<_>>()
        .ok_or(PythonNeeded::Arguments)?;
    let use_color: bool =
        !arguments.iter().any(|argument| argument == NO_COLOR_OPTION) && stdout_supports_color();
    let settings: ArgvSettings = ArgvSettings {
        columns: terminal_columns()?,
        use_color,
    };
    let mut host: NativeArgvHost = NativeArgvHost::default();
    let outcome: ArgvOutcome =
        parse_cli_arguments(&arguments, namespace_defaults(), settings, &mut host);
    if host.needs_python {
        return Err(PythonNeeded::Arguments);
    }
    let namespace: Namespace = match outcome.parsed {
        Err(code) => {
            for (stream, text) in &outcome.writes {
                write_text(*stream, text);
            }
            return Ok(i32::try_from(code).unwrap_or(1));
        }
        Ok(namespace) if outcome.writes.is_empty() => namespace,
        Ok(_) => return Err(PythonNeeded::Arguments),
    };
    let invocation: NativeInvocation = native_invocation(&namespace)?;
    run_command(&invocation, python_cli, use_color)
}
