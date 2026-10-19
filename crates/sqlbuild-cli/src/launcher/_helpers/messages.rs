//! The launcher's own lines on the standard streams, written as the Python CLI writes text.

use std::io::{self, Write};
use std::path::Path;

use crate::launcher::constants::{PROGRAM_NAME, PROGRAM_VERSION, PYTHON_CLI_SCRIPT};

/// argparse's `--version` line: `sqb <version>`.
pub(crate) fn version_line() -> String {
    format!("{PROGRAM_NAME} {PROGRAM_VERSION}\n")
}

/// Print the `--version` line on stdout.
pub(crate) fn print_version() {
    let _ = io::stdout().write_all(version_line().as_bytes());
}

/// The Python CLI script is not installed beside this program.
pub(crate) fn report_missing_python_cli(program: &Path) {
    let _ = writeln!(
        io::stderr(),
        "{PROGRAM_NAME}: cannot find the SQLBuild Python CLI ({PYTHON_CLI_SCRIPT}) beside {}",
        program.display()
    );
}

/// The Python CLI script exists but could not be started.
pub(crate) fn report_handoff_failure(script: &Path, error: &io::Error) {
    let _ = writeln!(
        io::stderr(),
        "{PROGRAM_NAME}: cannot start the SQLBuild Python CLI at {}: {error}",
        script.display()
    );
}
