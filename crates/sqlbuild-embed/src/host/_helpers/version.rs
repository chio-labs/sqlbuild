//! Checking the version a loaded libpython reports.

use crate::host::_helpers::installation::{minor_version, release_version};
use crate::host::constants::{FREE_THREADING_MARKER, SUPPORTED_MINOR_VERSIONS};

/// Accept `reported` (`Py_GetVersion()`) when it is a supported release matching `expected`.
pub(crate) fn check_version(reported: &str, expected: &str) -> Result<(), String> {
    let release: String = reported
        .split_whitespace()
        .next()
        .and_then(release_version)
        .ok_or_else(|| format!("libpython reports an unreadable version {reported:?}"))?;
    if reported.contains(FREE_THREADING_MARKER) {
        return Err(format!("libpython {release} is a free-threaded build"));
    }
    let supported: bool =
        minor_version(&release).is_some_and(|minor| SUPPORTED_MINOR_VERSIONS.contains(&minor));
    if !supported {
        return Err(format!(
            "libpython {release} is not a supported Python version"
        ));
    }
    let matches: bool = release
        .split('.')
        .zip(expected.split('.'))
        .all(|(reported, expected)| reported == expected);
    if !matches {
        return Err(format!(
            "libpython {release} does not match the interpreter's Python {expected}"
        ));
    }
    Ok(())
}
