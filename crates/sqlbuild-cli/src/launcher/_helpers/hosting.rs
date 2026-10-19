//! Start the Python CLI: in this process when its interpreter allows it, otherwise by `exec`.

use std::ffi::OsString;
use std::path::{Path, PathBuf};

use sqlbuild_embed::host::main::discover_host::discover_host;
use sqlbuild_embed::host::main::forget_host::forget_host;
use sqlbuild_embed::host::main::host_cache_root::host_cache_root;
use sqlbuild_embed::host::main::start_embedded::start_embedded;
use sqlbuild_embed::host::models::HostDiscovery;

use crate::launcher::_helpers::handoff::hand_off;
use crate::launcher::_helpers::messages::{report_embedding_failure, report_unknown_host_mode};
use crate::launcher::constants::{
    EMBEDDED_HOST_MODE, EXEC_HOST_MODE, HANDOFF_FAILURE_EXIT_CODE, HOST_MODE_VARIABLE,
    HOST_REPORT_VARIABLE,
};

/// How `SQLBUILD_HOST_MODE` asks `sqb` to start Python.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum HostMode {
    /// In this process when possible, otherwise by `exec`.
    Automatic,
    /// In this process, or fail.
    Embedded,
    /// Always by `exec`.
    Exec,
}

/// The host mode `value` of `SQLBUILD_HOST_MODE` selects, or `None` for an unknown value.
pub(crate) fn host_mode(value: Option<&std::ffi::OsStr>) -> Option<HostMode> {
    match value.map(|value| value.to_str()) {
        None => Some(HostMode::Automatic),
        Some(Some("")) => Some(HostMode::Automatic),
        Some(Some(EMBEDDED_HOST_MODE)) => Some(HostMode::Embedded),
        Some(Some(EXEC_HOST_MODE)) => Some(HostMode::Exec),
        Some(_) => None,
    }
}

/// CPython's arguments after `argv[0]`: the script and its arguments, exactly as `exec` passes them.
pub(crate) fn hosted_arguments(script: &Path, handed: &[OsString]) -> Vec<OsString> {
    std::iter::once(script.as_os_str().to_owned())
        .chain(handed.iter().cloned())
        .collect()
}

/// Run the Python CLI in this process; the reason it could not start otherwise.
fn run_embedded(script: &Path, handed: &[OsString]) -> Result<i32, String> {
    let cache_root: Option<PathBuf> = host_cache_root();
    let found = match discover_host(script, cache_root.as_deref()) {
        HostDiscovery::Embeddable(found) => found,
        HostDiscovery::Exec(reason) => return Err(reason),
    };
    let report = format!("embedded (libpython {})", found.library.display());
    start_embedded(
        &found,
        &hosted_arguments(script, handed),
        &[(HOST_REPORT_VARIABLE, &report)],
    )
    .map_err(|failure| {
        forget_host(cache_root.as_deref(), &found.interpreter);
        failure.reason
    })
}

/// Run the Python CLI script at `script` with `handed` for its exit code; before any thread starts.
pub(crate) fn run_python_cli(script: &Path, handed: &[OsString]) -> i32 {
    let Some(mode) = host_mode(std::env::var_os(HOST_MODE_VARIABLE).as_deref()) else {
        report_unknown_host_mode();
        return HANDOFF_FAILURE_EXIT_CODE;
    };
    let reason: String = match mode {
        HostMode::Exec => format!("{HOST_MODE_VARIABLE}={EXEC_HOST_MODE}"),
        HostMode::Automatic | HostMode::Embedded => match run_embedded(script, handed) {
            Ok(code) => return code,
            Err(reason) => reason,
        },
    };
    if mode == HostMode::Embedded {
        report_embedding_failure(&reason);
        return HANDOFF_FAILURE_EXIT_CODE;
    }
    hand_off(script, handed, &format!("exec ({reason})"))
}
