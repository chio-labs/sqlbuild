//! The launcher's own lines on the standard streams, written as the Python CLI writes text.

use std::io::{self, Write};
use std::path::Path;

use crate::launcher::constants::{
    EMBEDDED_HOST_MODE, EXEC_HOST_MODE, HOST_MODE_VARIABLE, PROGRAM_NAME, PYTHON_CLI_SCRIPT,
};

/// argparse's `--version` line: `sqb <version>` on stdout.
pub(crate) fn print_version() {
    let _ = writeln!(io::stdout(), "{PROGRAM_NAME} {}", env!("CARGO_PKG_VERSION"));
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

/// `SQLBUILD_HOST_MODE` has a value other than the two it accepts.
pub(crate) fn report_unknown_host_mode() {
    let _ = writeln!(
        io::stderr(),
        "{PROGRAM_NAME}: {HOST_MODE_VARIABLE} must be {EMBEDDED_HOST_MODE} or {EXEC_HOST_MODE}"
    );
}

/// `SQLBUILD_HOST_MODE=embedded` asked for Python in this process, which is not possible.
pub(crate) fn report_embedding_failure(reason: &str) {
    let _ = writeln!(
        io::stderr(),
        "{PROGRAM_NAME}: cannot start the SQLBuild Python CLI in this process: {reason}"
    );
}
