//! Caller-requested JSON output.

use crate::dagster_invocation::constants::{JSON_OUTPUT_FLAG, JSON_OUTPUT_FLAGS};

/// Whether the arguments already request JSON output.
#[must_use]
pub fn json_output_requested(args: &[String]) -> bool {
    let prefix: String = format!("{JSON_OUTPUT_FLAG}=");
    args.iter().any(|argument| {
        JSON_OUTPUT_FLAGS.contains(&argument.as_str()) || argument.starts_with(&prefix)
    })
}
