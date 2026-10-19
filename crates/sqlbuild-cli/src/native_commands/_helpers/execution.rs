//! Running a Python-free command: its checks, then its output with the observed services.

use std::io;
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use crate::argv::models::Stream;
use crate::compute_logs::constants::DEFAULT_RETENTION_COUNT;
use crate::compute_logs::main::finish_capture::finish_capture;
use crate::compute_logs::main::open_log_root::open_log_root;
use crate::compute_logs::main::start_capture::start_capture;
use crate::compute_logs::models::{CaptureEnd, CaptureStart, OpenCapture};
use crate::native_commands::_helpers::init::run_init;
use crate::native_commands::_helpers::package::installed_package;
use crate::native_commands::_helpers::paths::project_location;
use crate::native_commands::_helpers::project_facts::has_no_runtime_extensions;
use crate::native_commands::_helpers::rules::run_rules;
use crate::native_commands::_helpers::skills::{run_skills, skill_freshness_notice};
use crate::native_commands::_helpers::terminal::{exit_on_interrupt, write_text};
use crate::native_commands::constants::UNKNOWN_COMMAND;
use crate::native_commands::errors::PythonNeeded;
use crate::native_commands::models::{
    CommandOutput, InstalledPackage, NativeCommand, NativeInvocation, ProjectLocation,
};

/// The capture Python's `dispatch_with_compute_logs` opens; a failure only loses the log.
fn open_capture(
    invocation: &NativeInvocation,
    project: &ProjectLocation,
    started_at: SystemTime,
) -> io::Result<OpenCapture> {
    let retention: i64 = i64::try_from(DEFAULT_RETENTION_COUNT).unwrap_or(i64::MAX);
    let root: PathBuf = open_log_root(&project.given, None, Some(retention))
        .map_err(|error| io::Error::other(format!("{error:?}")))?;
    start_capture(CaptureStart {
        root,
        command: invocation
            .command_name
            .clone()
            .unwrap_or_else(|| UNKNOWN_COMMAND.to_owned()),
        project_dir: project.resolved.display().to_string(),
        target: invocation.target.clone(),
        started_at,
    })
}

/// Print an observed command's output after the skill notice, retaining both in its capture.
fn finish_observed(
    invocation: &NativeInvocation,
    (project, package): (&ProjectLocation, &InstalledPackage),
    started_at: SystemTime,
    output: CommandOutput,
) -> i32 {
    let notice: String = if invocation.maintains_skills {
        skill_freshness_notice(&project.given, package)
    } else {
        String::new()
    };
    let capture: io::Result<OpenCapture> = open_capture(invocation, project, started_at);
    let stderr: String = notice + &output.stderr;
    write_text(Stream::Stderr, &stderr);
    write_text(Stream::Stdout, &output.stdout);
    if let Ok(capture) = capture {
        let finished: io::Result<()> = finish_capture(
            capture,
            &CaptureEnd {
                stdout: output.stdout.into_bytes(),
                stderr: stderr.into_bytes(),
                exit_code: i64::from(output.exit_code),
            },
        );
        drop(finished);
    }
    output.exit_code
}

/// What an observed command prints, unless it needs Python after all.
fn observed_output(
    command: &NativeCommand,
    project: &ProjectLocation,
    package: &InstalledPackage,
) -> Result<CommandOutput, PythonNeeded> {
    if !has_no_runtime_extensions(&project.given) {
        return Err(PythonNeeded::Project);
    }
    match command {
        NativeCommand::Nothing => Ok(CommandOutput::default()),
        NativeCommand::Skills(options) => run_skills(&project.resolved, package, options),
        NativeCommand::Rules(options) => run_rules(&project.resolved, options),
        NativeCommand::Init => Err(PythonNeeded::Command),
    }
}

/// Run a parsed Python-free command; an error hands it to Python before any side effect.
pub(crate) fn run_command(
    invocation: &NativeInvocation,
    python_cli: &Path,
    error_color: bool,
) -> Result<i32, PythonNeeded> {
    exit_on_interrupt();
    let package: InstalledPackage = installed_package(python_cli)?;
    let project: ProjectLocation = project_location(invocation.project_dir.as_deref())?;
    if invocation.creates_project {
        let output: CommandOutput = run_init(&project.resolved, &package, error_color)?;
        write_text(Stream::Stderr, &output.stderr);
        write_text(Stream::Stdout, &output.stdout);
        return Ok(output.exit_code);
    }
    let started_at: SystemTime = SystemTime::now();
    let output: CommandOutput = observed_output(&invocation.command, &project, &package)?;
    Ok(finish_observed(
        invocation,
        (&project, &package),
        started_at,
        output,
    ))
}
