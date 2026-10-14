//! The plan's dbt and SQLBuild command lines.

use crate::dbt_cli::main::build_dbt_argv::build_dbt_argv;
use crate::dbt_cli::models::{DbtArgvCommand, DbtInteropCommandKind};
use crate::dbt_plan::models::{DbtPlanArgvRequest, DbtPlanArgvs};

/// `dbt ls` for plans, the command itself otherwise; SQLBuild runs models with `build` minus tests.
#[must_use]
pub fn dbt_plan_argvs(request: &DbtPlanArgvRequest<'_>) -> DbtPlanArgvs {
    let dbt_command: &str = match request.command {
        DbtInteropCommandKind::Plan => "ls",
        command => command.name(),
    };
    let mut dbt_command_argv: Vec<String> =
        vec![request.dbt_executable.to_owned(), dbt_command.to_owned()];
    dbt_command_argv.extend(request.dbt_command_args.iter().cloned());
    let mut sqlbuild_command_argvs: Vec<Vec<String>> = Vec::new();
    if !request.selected_model_names.is_empty() {
        let sqlbuild_command: &[&str] = match request.command {
            DbtInteropCommandKind::Run => &["build", "--no-tests", "--no-audits"],
            command => &[command.name()],
        };
        let mut argv: Vec<String> = vec![request.sqlbuild_executable.to_owned()];
        argv.extend(sqlbuild_command.iter().map(|part| (*part).to_owned()));
        argv.push("--select".to_owned());
        argv.extend(request.selected_model_names.iter().cloned());
        argv.extend(request.sqlbuild_command_args.iter().cloned());
        sqlbuild_command_argvs.push(argv);
    }
    let mut supplemental_dbt_command_argvs: Vec<Vec<String>> = Vec::new();
    if !request.required_selector_terms.is_empty() {
        let mut args: Vec<String> = vec!["--select".to_owned()];
        args.extend(request.required_selector_terms.iter().cloned());
        supplemental_dbt_command_argvs.push(build_dbt_argv(
            request.dbt_executable,
            request.options,
            DbtArgvCommand::Other {
                command: dbt_command.to_owned(),
                args,
            },
        ));
    }
    DbtPlanArgvs {
        dbt_command_argv,
        sqlbuild_command_argvs,
        supplemental_dbt_command_argvs,
    }
}
