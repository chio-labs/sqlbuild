//! The `ingestr ingest` arguments for one source run.

use crate::ingestr_command::constants::{COMMAND_PREFIX, COMMAND_PROGRESS};
use crate::ingestr_command::models::{IngestrDestination, IngestrSource};

/// The ingestr command line that loads `source` into `destination`.
#[must_use]
pub fn ingestr_command_arguments(
    source: &IngestrSource,
    destination: &IngestrDestination,
) -> Vec<String> {
    let mut arguments: Vec<String> = COMMAND_PREFIX.map(str::to_owned).to_vec();
    let pairs: [(&str, &str); 4] = [
        ("--source-uri", &source.source_uri),
        ("--source-table", &source.source_table),
        ("--dest-uri", &destination.uri),
        ("--dest-table", &destination.table),
    ];
    let optional: [(&str, Option<&String>); 2] = [
        ("--incremental-strategy", source.strategy.as_ref()),
        ("--incremental-key", source.incremental_key.as_ref()),
    ];
    for (flag, value) in pairs {
        arguments.extend([flag.to_owned(), value.to_owned()]);
    }
    arguments.extend(COMMAND_PROGRESS.map(str::to_owned));
    for (flag, value) in optional {
        if let Some(value) = value {
            arguments.extend([flag.to_owned(), value.clone()]);
        }
    }
    for primary_key in &source.primary_key {
        arguments.extend(["--primary-key".to_owned(), primary_key.clone()]);
    }
    if let Some(columns) = &source.columns {
        arguments.extend(["--columns".to_owned(), columns.clone()]);
    }
    if destination.is_reload {
        arguments.push("--full-refresh".to_owned());
    }
    arguments.extend(source.extra_args.iter().cloned());
    arguments
}
