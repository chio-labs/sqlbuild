//! Forwarded dbt arguments with path values marked for re-rooting.

use crate::dbt_command::constants::PATH_VALUE_OPTIONS;
use crate::dbt_command::models::ForwardedArg;

/// Every argument, with the value after a path flag marked as a path.
#[must_use]
pub fn forwarded_dbt_args(args: &[String]) -> Vec<ForwardedArg> {
    let mut forwarded: Vec<ForwardedArg> = Vec::new();
    let mut index: usize = 0;
    while index < args.len() {
        let arg: &String = &args[index];
        forwarded.push(ForwardedArg::Literal(arg.clone()));
        index += 1;
        if PATH_VALUE_OPTIONS.contains(&arg.as_str())
            && let Some(value) = args.get(index)
        {
            forwarded.push(ForwardedArg::Path(value.clone()));
            index += 1;
        }
    }
    forwarded
}
