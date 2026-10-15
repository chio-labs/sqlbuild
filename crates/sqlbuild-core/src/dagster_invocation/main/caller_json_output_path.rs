//! The JSON output path a caller passed.

use crate::dagster_invocation::constants::JSON_OUTPUT_FLAG;

/// The first `--json-output PATH` or `--json-output=PATH` value.
#[must_use]
pub fn caller_json_output_path(args: &[String]) -> Option<String> {
    let prefix: String = format!("{JSON_OUTPUT_FLAG}=");
    for (index, argument) in args.iter().enumerate() {
        if argument == JSON_OUTPUT_FLAG
            && let Some(path) = args.get(index + 1)
        {
            return Some(path.clone());
        }
        if let Some(path) = argument.strip_prefix(&prefix)
            && !path.is_empty()
        {
            return Some(path.to_owned());
        }
    }
    None
}
