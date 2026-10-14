//! Build the argv of one dbt command.

use crate::dbt_cli::_helpers::argv::{with_common_options, with_deps_options};
use crate::dbt_cli::models::{DbtArgvCommand, DbtCliOptionValues};

/// `dbt_executable <command> <options...> <command args...>`.
#[must_use]
pub fn build_dbt_argv(
    dbt_executable: &str,
    options: &DbtCliOptionValues,
    command: DbtArgvCommand,
) -> Vec<String> {
    let start = |names: &[&str]| -> Vec<String> {
        std::iter::once(dbt_executable)
            .chain(names.iter().copied())
            .map(str::to_owned)
            .collect()
    };
    match command {
        DbtArgvCommand::Compile { full_refresh } => {
            let mut argv: Vec<String> = with_common_options(start(&["compile"]), options);
            if full_refresh {
                argv.push("--full-refresh".to_owned());
            }
            argv
        }
        DbtArgvCommand::Deps => with_deps_options(start(&["deps"]), options),
        DbtArgvCommand::Debug { args } => {
            let mut argv: Vec<String> = with_common_options(start(&["debug"]), options);
            argv.extend(args);
            argv
        }
        DbtArgvCommand::Other { command, args } => {
            let mut argv: Vec<String> = with_common_options(start(&[&command]), options);
            argv.extend(args);
            argv
        }
        DbtArgvCommand::Ls {
            select,
            exclude,
            resource_types,
        } => {
            let mut argv: Vec<String> =
                with_common_options(start(&["ls", "--output", "json"]), options);
            if !select.is_empty() {
                argv.push("--select".to_owned());
                argv.extend(select);
            }
            if !exclude.is_empty() {
                argv.push("--exclude".to_owned());
                argv.extend(exclude);
            }
            for resource_type in resource_types {
                argv.push("--resource-type".to_owned());
                argv.push(resource_type);
            }
            argv
        }
    }
}
