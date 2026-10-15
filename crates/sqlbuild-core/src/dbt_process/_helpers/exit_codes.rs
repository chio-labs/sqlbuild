//! `subprocess` return codes from exit statuses.

use std::process::ExitStatus;

/// The exit code, or the negated signal number of a signalled process.
pub(crate) fn returncode(status: ExitStatus) -> i64 {
    if let Some(code) = status.code() {
        return i64::from(code);
    }
    signal_returncode(status)
}

#[cfg(unix)]
fn signal_returncode(status: ExitStatus) -> i64 {
    use std::os::unix::process::ExitStatusExt;
    status.signal().map_or(-1, |signal| -i64::from(signal))
}

#[cfg(not(unix))]
fn signal_returncode(_status: ExitStatus) -> i64 {
    -1
}
