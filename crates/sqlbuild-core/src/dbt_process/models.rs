//! A finished captured dbt command and a running dbt JSON log stream.

use std::io::{BufReader, PipeReader};
use std::process::Child;

/// Exit code (negative signal numbers for signalled processes) and decoded output.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct DbtProcessOutput {
    pub returncode: i64,
    pub stdout: String,
    pub stderr: String,
}

/// A running dbt process whose stdout and stderr share one line reader.
#[derive(Debug)]
pub struct DbtJsonProcess {
    pub child: Child,
    pub output: BufReader<PipeReader>,
}
