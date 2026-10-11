//! Find the Python CLI script installed beside this program and run it with the same arguments.

use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::process::Command;

use crate::launcher::_helpers::messages::report_handoff_failure;
use crate::launcher::constants::{HANDOFF_FAILURE_EXIT_CODE, PYTHON_CLI_SCRIPT};

/// The Python CLI script beside this program or beside the file it links to.
pub(crate) fn python_cli(program: &Path) -> Option<PathBuf> {
    let resolved = std::fs::canonicalize(program).unwrap_or_else(|_| program.to_path_buf());
    [program, resolved.as_path()]
        .into_iter()
        .filter_map(Path::parent)
        .map(|directory| directory.join(PYTHON_CLI_SCRIPT))
        .find(|candidate| candidate.is_file())
}

fn failure(script: &Path, error: &std::io::Error) -> i32 {
    report_handoff_failure(script, error);
    HANDOFF_FAILURE_EXIT_CODE
}

/// Replace this process with the Python CLI; returns only when it cannot start.
#[cfg(unix)]
pub(crate) fn hand_off(script: &Path, arguments: &[OsString]) -> i32 {
    use std::os::unix::process::CommandExt;

    let error = Command::new(script).args(arguments).exec();
    failure(script, &error)
}

/// Run the Python CLI as a child that alone handles Ctrl+C, and return its exit code.
#[cfg(not(unix))]
pub(crate) fn hand_off(script: &Path, arguments: &[OsString]) -> i32 {
    let _ = ctrlc::set_handler(|| {});
    match Command::new(script).args(arguments).status() {
        Ok(status) => status.code().unwrap_or(HANDOFF_FAILURE_EXIT_CODE),
        Err(error) => failure(script, &error),
    }
}
