//! Strip SQLBuild-owned debug and configuration flags before invoking dbt.

use crate::dbt_cli::constants::DBT_NO_CONNECTION_FLAG;

/// Preserve dbt arguments while removing the configuration flags already resolved by SQLBuild.
pub fn dbt_debug_args(args: &[String]) -> Vec<String> {
    let mut stripped: Vec<String> = Vec::new();
    let mut skip_next = false;
    for arg in args {
        if skip_next {
            skip_next = false;
        } else if matches!(
            arg.as_str(),
            "--project-dir" | "--profiles-dir" | "--target" | "--target-path"
        ) {
            skip_next = true;
        } else if arg != DBT_NO_CONNECTION_FLAG {
            stripped.push(arg.clone());
        }
    }
    stripped
}
