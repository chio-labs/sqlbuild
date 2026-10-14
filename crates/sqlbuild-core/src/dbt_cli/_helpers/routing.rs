//! `sqb dbt` flag validation and the dbt and SQLBuild argument buckets.

use crate::dbt_cli::constants::{
    EVENT_TIME_CURSOR_CONFLICT_CODE, EVENT_TIME_CURSOR_CONFLICT_HELP, EVENT_TIME_PAIR_CODE,
    EXECUTION_SQLBUILD_FLAGS, PLAN_SQLBUILD_FLAGS, SQLBUILD_FLAG_CODE,
};
use crate::dbt_cli::errors::DbtCliError;
use crate::dbt_cli::models::{DbtInteropCommandKind, DbtParsedFlags, DbtRoutedArgs};

fn maps_to_sqlbuild(command: DbtInteropCommandKind) -> bool {
    command != DbtInteropCommandKind::Debug
}

fn pushed(mut args: Vec<String>, values: &[&str]) -> Vec<String> {
    args.extend(values.iter().map(|value| (*value).to_owned()));
    args
}

fn allowed_sqlbuild_flags(command: DbtInteropCommandKind) -> &'static [&'static str] {
    match command {
        DbtInteropCommandKind::Run | DbtInteropCommandKind::Build => &EXECUTION_SQLBUILD_FLAGS,
        DbtInteropCommandKind::Plan => &PLAN_SQLBUILD_FLAGS,
        DbtInteropCommandKind::Debug => &[],
    }
}

/// Reject an event-time start without an end, or the reverse.
pub(crate) fn check_event_time_pair(flags: &DbtParsedFlags) -> Result<(), DbtCliError> {
    if flags.event_time_start.is_none() == flags.event_time_end.is_none() {
        return Ok(());
    }
    Err(DbtCliError {
        message: "--event-time-start and --event-time-end must be provided together".to_owned(),
        code: Some(EVENT_TIME_PAIR_CODE),
        help: None,
    })
}

/// Reject SQLBuild-only flags the command does not accept.
pub(crate) fn check_sqlbuild_flags(
    command: DbtInteropCommandKind,
    flags: &DbtParsedFlags,
) -> Result<(), DbtCliError> {
    let allowed: &[&str] = allowed_sqlbuild_flags(command);
    let present: [(&str, bool); 7] = [
        ("--start-cursor-ts", flags.start_cursor_ts.is_some()),
        ("--end-cursor-ts", flags.end_cursor_ts.is_some()),
        ("--start-cursor-int", flags.start_cursor_int.is_some()),
        ("--end-cursor-int", flags.end_cursor_int.is_some()),
        ("--defer-to", flags.defer_to.is_some()),
        ("--fail-fast", flags.fail_fast),
        ("--hard-copy", flags.hard_copy),
    ];
    match present
        .into_iter()
        .find(|(flag, present)| *present && !allowed.contains(flag))
    {
        Some((flag, _)) => Err(DbtCliError {
            message: format!(
                "{flag} is not a valid SQLBuild option for sqb dbt {}",
                command.name()
            ),
            code: Some(SQLBUILD_FLAG_CODE),
            help: None,
        }),
        None => Ok(()),
    }
}

/// Reject dbt event-time flags combined with SQLBuild timestamp cursors.
pub(crate) fn check_event_time_cursors(
    command: DbtInteropCommandKind,
    flags: &DbtParsedFlags,
) -> Result<(), DbtCliError> {
    if flags.event_time_start.is_none() || !maps_to_sqlbuild(command) {
        return Ok(());
    }
    if flags.start_cursor_ts.is_none() && flags.end_cursor_ts.is_none() {
        return Ok(());
    }
    Err(DbtCliError {
        message: "--event-time-start/end conflict with --start-cursor-ts/end-cursor-ts".to_owned(),
        code: Some(EVENT_TIME_CURSOR_CONFLICT_CODE),
        help: Some(EVENT_TIME_CURSOR_CONFLICT_HELP),
    })
}

/// Selection flags, then flags both tools receive, in routing order.
pub(crate) fn shared_args(
    command: DbtInteropCommandKind,
    flags: &DbtParsedFlags,
    routed: DbtRoutedArgs,
) -> DbtRoutedArgs {
    let DbtRoutedArgs {
        mut dbt_args,
        mut sqlbuild_args,
    } = routed;
    if !flags.select.is_empty() {
        dbt_args.push("--select".to_owned());
        dbt_args.extend(flags.select.iter().cloned());
    }
    if !flags.exclude.is_empty() {
        dbt_args.push("--exclude".to_owned());
        dbt_args.extend(flags.exclude.iter().cloned());
    }
    if let Some(vars) = &flags.vars {
        dbt_args = pushed(dbt_args, &["--vars", vars]);
        sqlbuild_args = pushed(sqlbuild_args, &["--vars", vars]);
    }
    if let Some(threads) = &flags.threads {
        dbt_args = pushed(dbt_args, &["--threads", threads]);
        sqlbuild_args = pushed(sqlbuild_args, &["--concurrency", threads]);
    }
    let to_sqlbuild: bool = maps_to_sqlbuild(command);
    if flags.full_refresh {
        dbt_args = pushed(dbt_args, &["--full-refresh"]);
        if to_sqlbuild {
            sqlbuild_args = pushed(sqlbuild_args, &["--full-refresh"]);
        }
    }
    for (value, dbt_flag, sqlbuild_flag) in [
        (
            &flags.event_time_start,
            "--event-time-start",
            "--start-cursor-ts",
        ),
        (&flags.event_time_end, "--event-time-end", "--end-cursor-ts"),
    ] {
        if let Some(value) = value {
            dbt_args = pushed(dbt_args, &[dbt_flag, value]);
            if to_sqlbuild {
                sqlbuild_args = pushed(sqlbuild_args, &[sqlbuild_flag, value]);
            }
        }
    }
    DbtRoutedArgs {
        dbt_args,
        sqlbuild_args,
    }
}

/// dbt configuration flags, then SQLBuild-only flags.
pub(crate) fn tool_args(flags: &DbtParsedFlags, routed: DbtRoutedArgs) -> DbtRoutedArgs {
    let DbtRoutedArgs {
        mut dbt_args,
        mut sqlbuild_args,
    } = routed;
    for (flag, value) in [
        ("--project-dir", &flags.project_dir),
        ("--profiles-dir", &flags.profiles_dir),
        ("--profile", &flags.profile),
        ("--target", &flags.target),
        ("--target-path", &flags.target_path),
        ("--state", &flags.state),
        ("--indirect-selection", &flags.indirect_selection),
    ] {
        if let Some(value) = value {
            dbt_args = pushed(dbt_args, &[flag, value]);
        }
    }
    if flags.defer {
        dbt_args = pushed(dbt_args, &["--defer"]);
    }
    for (flag, value) in [
        ("--start-cursor-ts", &flags.start_cursor_ts),
        ("--end-cursor-ts", &flags.end_cursor_ts),
        ("--start-cursor-int", &flags.start_cursor_int),
        ("--end-cursor-int", &flags.end_cursor_int),
        ("--defer-to", &flags.defer_to),
    ] {
        if let Some(value) = value {
            sqlbuild_args = pushed(sqlbuild_args, &[flag, value]);
        }
    }
    for (flag, enabled) in [
        ("--fail-fast", flags.fail_fast),
        ("--hard-copy", flags.hard_copy),
    ] {
        if enabled {
            sqlbuild_args = pushed(sqlbuild_args, &[flag]);
        }
    }
    DbtRoutedArgs {
        dbt_args,
        sqlbuild_args,
    }
}
