//! Split parsed `sqb dbt` flags into dbt and SQLBuild arguments.

use crate::dbt_cli::_helpers::routing::{
    check_event_time_cursors, check_event_time_pair, check_sqlbuild_flags, shared_args, tool_args,
};
use crate::dbt_cli::constants::UNSUPPORTED_COMMAND_CODE;
use crate::dbt_cli::errors::DbtCliError;
use crate::dbt_cli::models::{DbtInteropCommandKind, DbtParsedFlags, DbtRoutedArgs};

/// The command and its routed argument buckets, dbt passthrough arguments last.
pub fn route_dbt_interop_args(
    command: &str,
    flags: &DbtParsedFlags,
) -> Result<(DbtInteropCommandKind, DbtRoutedArgs), DbtCliError> {
    let kind: DbtInteropCommandKind = match command {
        "plan" => DbtInteropCommandKind::Plan,
        "run" => DbtInteropCommandKind::Run,
        "build" => DbtInteropCommandKind::Build,
        "debug" => DbtInteropCommandKind::Debug,
        _ => {
            return Err(DbtCliError {
                message: format!("Unsupported sqb dbt command: {command}"),
                code: Some(UNSUPPORTED_COMMAND_CODE),
                help: None,
            });
        }
    };
    check_event_time_pair(flags)?;
    check_sqlbuild_flags(kind, flags)?;
    let routed: DbtRoutedArgs =
        tool_args(flags, shared_args(kind, flags, DbtRoutedArgs::default()));
    check_event_time_cursors(kind, flags)?;
    let mut routed: DbtRoutedArgs = routed;
    routed
        .dbt_args
        .extend(flags.dbt_passthrough.iter().cloned());
    Ok((kind, routed))
}
