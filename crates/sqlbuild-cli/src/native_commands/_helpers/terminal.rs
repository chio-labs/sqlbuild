//! The process's terminal: its width, colour support, stream writes and Ctrl+C.

use std::io::{self, IsTerminal, Write};

use crate::argv::models::Stream;
use crate::native_commands::_helpers::argv_host::python_int;
use crate::native_commands::constants::{COLUMNS_VARIABLE, FALLBACK_COLUMNS, NO_COLOR_VARIABLE};
use crate::native_commands::errors::PythonNeeded;

/// `int(os.environ["COLUMNS"])`, `0` when unset or not an integer; beyond 64 bits is Python's.
fn columns_variable() -> Result<i64, PythonNeeded> {
    let Ok(text) = std::env::var(COLUMNS_VARIABLE) else {
        return Ok(0);
    };
    let Some(number) = python_int(&text) else {
        return Ok(0);
    };
    number.parse::<i64>().map_err(|_| PythonNeeded::Arguments)
}

/// The width of the terminal on stdout, or the fallback when stdout is not one.
#[cfg(unix)]
fn stdout_columns() -> Result<i64, PythonNeeded> {
    match rustix::termios::tcgetwinsize(io::stdout()) {
        Ok(size) if size.ws_col > 0 => Ok(i64::from(size.ws_col)),
        _ => Ok(FALLBACK_COLUMNS),
    }
}

/// A console's width needs the console API; only a redirected stdout has a known width.
#[cfg(not(unix))]
fn stdout_columns() -> Result<i64, PythonNeeded> {
    if io::stdout().is_terminal() {
        return Err(PythonNeeded::Arguments);
    }
    Ok(FALLBACK_COLUMNS)
}

/// `shutil.get_terminal_size().columns`, unless only Python can tell.
pub(crate) fn terminal_columns() -> Result<i64, PythonNeeded> {
    let columns: i64 = columns_variable()?;
    if columns > 0 {
        return Ok(columns);
    }
    stdout_columns()
}

/// `stdout_supports_color`: stdout is a terminal and `NO_COLOR` is unset.
pub(crate) fn stdout_supports_color() -> bool {
    std::env::var_os(NO_COLOR_VARIABLE).is_none() && io::stdout().is_terminal()
}

/// `\n` as a Python text stream writes it on this platform.
fn console_bytes(text: &str) -> Vec<u8> {
    if cfg!(windows) {
        text.replace('\n', "\r\n").into_bytes()
    } else {
        text.as_bytes().to_vec()
    }
}

/// Write and flush one text; a closed or full stream drops it, as the parse's writes do.
pub(crate) fn write_text(stream: Stream, text: &str) {
    if text.is_empty() {
        return;
    }
    let bytes: Vec<u8> = console_bytes(text);
    let written: io::Result<()> = match stream {
        Stream::Stdout => {
            let mut output = io::stdout().lock();
            output.write_all(&bytes).and_then(|()| output.flush())
        }
        Stream::Stderr => {
            let mut output = io::stderr().lock();
            output.write_all(&bytes).and_then(|()| output.flush())
        }
    };
    drop(written);
}

/// End the process with status 130 on Ctrl+C; handing off by `exec` restores the default.
#[cfg(unix)]
pub(crate) fn exit_on_interrupt() {
    use crate::native_commands::constants::INTERRUPTED_EXIT_CODE;

    drop(ctrlc::set_handler(|| {
        std::process::exit(INTERRUPTED_EXIT_CODE)
    }));
}

/// The Python child waited for alone handles Ctrl+C, so the native command keeps the default.
#[cfg(not(unix))]
pub(crate) fn exit_on_interrupt() {}
