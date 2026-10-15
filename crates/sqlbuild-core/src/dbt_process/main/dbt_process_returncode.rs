//! Wait for a dbt process and report its `subprocess` return code.

use std::io;
use std::process::Child;

use crate::dbt_process::_helpers::exit_codes::returncode;

/// The exit code, or the negated signal number, once the process has ended.
pub fn dbt_process_returncode(child: &mut Child) -> io::Result<i64> {
    Ok(returncode(child.wait()?))
}
