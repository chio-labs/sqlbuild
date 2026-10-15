//! Run one dbt command to completion with its output captured as text.

use std::io;
use std::path::Path;
use std::process::{Command, Output};

use crate::dbt_process::_helpers::exit_codes::returncode;
use crate::dbt_process::_helpers::text::universal_text;
use crate::dbt_process::models::DbtProcessOutput;

/// `subprocess.run(argv, cwd=cwd, capture_output=True, text=True)`.
pub fn run_dbt_process(argv: &[String], cwd: Option<&Path>) -> io::Result<DbtProcessOutput> {
    let Some((program, arguments)) = argv.split_first() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "empty dbt argv",
        ));
    };
    let mut command: Command = Command::new(program);
    command.args(arguments);
    if let Some(directory) = cwd {
        command.current_dir(directory);
    }
    let output: Output = command.output()?;
    Ok(DbtProcessOutput {
        returncode: returncode(output.status),
        stdout: universal_text(&output.stdout),
        stderr: universal_text(&output.stderr),
    })
}
