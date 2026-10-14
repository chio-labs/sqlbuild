//! The detail shown for a failed dbt command.

use crate::text::main::python_strip::python_strip;

/// Stripped stderr, or stdout when stderr is empty; `None` when nothing remains.
#[must_use]
pub fn dbt_failure_detail(stderr: &str, stdout: &str) -> Option<String> {
    let output: &str = if stderr.is_empty() { stdout } else { stderr };
    let detail: &str = python_strip(output);
    (!detail.is_empty()).then(|| detail.to_owned())
}
