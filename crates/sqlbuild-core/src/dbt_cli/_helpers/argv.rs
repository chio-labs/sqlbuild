//! dbt options rendered as command-line flags.

use crate::dbt_cli::models::DbtCliOptionValues;

fn with_value(mut argv: Vec<String>, flag: &str, value: Option<&String>) -> Vec<String> {
    if let Some(value) = value {
        argv.push(flag.to_owned());
        argv.push(value.clone());
    }
    argv
}

/// `argv` followed by every set common option, in dbt's documented order.
pub(crate) fn with_common_options(argv: Vec<String>, options: &DbtCliOptionValues) -> Vec<String> {
    let argv: Vec<String> = with_value(argv, "--project-dir", options.project_dir.as_ref());
    let argv: Vec<String> = with_value(argv, "--profiles-dir", options.profiles_dir.as_ref());
    let argv: Vec<String> = with_value(argv, "--target", options.target.as_ref());
    let argv: Vec<String> = with_value(argv, "--target-path", options.target_path.as_ref());
    let argv: Vec<String> = with_value(argv, "--vars", options.vars.as_ref());
    let mut argv: Vec<String> = with_value(argv, "--state", options.state.as_ref());
    if options.defer {
        argv.push("--defer".to_owned());
    }
    argv
}

/// `argv` followed by the options `dbt deps` accepts.
pub(crate) fn with_deps_options(argv: Vec<String>, options: &DbtCliOptionValues) -> Vec<String> {
    let argv: Vec<String> = with_value(argv, "--project-dir", options.project_dir.as_ref());
    let argv: Vec<String> = with_value(argv, "--profiles-dir", options.profiles_dir.as_ref());
    let argv: Vec<String> = with_value(argv, "--target", options.target.as_ref());
    with_value(argv, "--vars", options.vars.as_ref())
}
