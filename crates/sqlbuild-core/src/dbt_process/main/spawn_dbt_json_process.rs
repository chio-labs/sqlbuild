//! Start dbt with JSON logs, its stdout and stderr merged into one line stream.

use std::io::{self, BufReader, PipeReader, PipeWriter};
use std::path::Path;
use std::process::{Command, Stdio};

use crate::dbt_process::constants::{DBT_JSON_ENVIRONMENT, DBT_TARGET_PATH_VARIABLES};
use crate::dbt_process::models::DbtJsonProcess;

/// Spawn `argv` in `cwd` with JSON logging and, when given, artifacts and logs below `target_path`.
pub fn spawn_dbt_json_process(
    argv: &[String],
    (cwd, target_path): (Option<&Path>, Option<&Path>),
) -> io::Result<DbtJsonProcess> {
    let Some((program, arguments)) = argv.split_first() else {
        return Err(io::Error::new(
            io::ErrorKind::InvalidInput,
            "empty dbt argv",
        ));
    };
    let (reader, writer): (PipeReader, PipeWriter) = io::pipe()?;
    let mut command: Command = Command::new(program);
    command
        .args(arguments)
        .envs(DBT_JSON_ENVIRONMENT)
        .stdout(Stdio::from(writer.try_clone()?))
        .stderr(Stdio::from(writer));
    if let Some(target) = target_path {
        for variable in DBT_TARGET_PATH_VARIABLES {
            command.env(variable, target);
        }
    }
    if let Some(directory) = cwd {
        command.current_dir(directory);
    }
    let child = command.spawn()?;
    drop(command);
    Ok(DbtJsonProcess {
        child,
        output: BufReader::new(reader),
    })
}
