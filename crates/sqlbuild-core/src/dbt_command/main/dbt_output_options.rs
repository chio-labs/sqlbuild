//! SQLBuild's own output flags among forwarded dbt arguments.

use crate::dbt_command::constants::{JSON_OPTION, VERBOSE_OPTIONS};
use crate::dbt_command::models::DbtOutputOptions;

/// Whether `--json` or a verbose flag was given, and the arguments without them.
#[must_use]
pub fn dbt_output_options(args: &[String]) -> DbtOutputOptions {
    let output_option =
        |arg: &String| arg == JSON_OPTION || VERBOSE_OPTIONS.contains(&arg.as_str());
    DbtOutputOptions {
        json_output: args.iter().any(|arg| arg == JSON_OPTION),
        verbose: args
            .iter()
            .any(|arg| VERBOSE_OPTIONS.contains(&arg.as_str())),
        routed_args: args
            .iter()
            .filter(|arg| !output_option(arg))
            .cloned()
            .collect(),
    }
}
