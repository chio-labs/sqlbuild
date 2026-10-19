//! Run the discovered interpreter's CPython `main` in this process.

use std::ffi::{CString, OsString};

use crate::host::_helpers::library::LoadedPython;
use crate::host::_helpers::version::check_version;
use crate::host::models::{EmbedFailure, EmbeddableInterpreter};

#[cfg(unix)]
fn c_argument(argument: &std::ffi::OsStr) -> Result<CString, String> {
    use std::os::unix::ffi::OsStrExt;
    CString::new(argument.as_bytes()).map_err(|_| "an argument contains a NUL byte".to_owned())
}

#[cfg(not(unix))]
fn c_argument(argument: &std::ffi::OsStr) -> Result<CString, String> {
    let text: &str = argument
        .to_str()
        .ok_or_else(|| "an argument is not Unicode".to_owned())?;
    CString::new(text).map_err(|_| "an argument contains a NUL byte".to_owned())
}

/// Run `python <arguments>` here for its exit status, or say why nothing ran; before any thread.
pub fn start_embedded(
    found: &EmbeddableInterpreter,
    arguments: &[OsString],
    environment: &[(&str, &str)],
) -> Result<i32, EmbedFailure> {
    let failure = |reason: String| EmbedFailure { reason };
    let argv: Vec<CString> = std::iter::once(found.interpreter.as_os_str())
        .chain(arguments.iter().map(OsString::as_os_str))
        .map(c_argument)
        .collect::<Result<_, _>>()
        .map_err(failure)?;
    let python: LoadedPython = LoadedPython::load(&found.library).map_err(failure)?;
    let reported: String = python.version().map_err(failure)?;
    check_version(&reported, &found.version).map_err(failure)?;
    python.run_main(&argv, environment).map_err(failure)
}
