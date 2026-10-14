//! Leave the launch record a later `sqb` reads to serve an unchanged compile natively.

use std::io;
use std::path::Path;

use crate::replay::_helpers::files::{prune_records, replace_file};

/// Atomically replace `path` with the record `text`, then prune the oldest records beside it.
pub fn write_launch_record(path: &Path, text: &str) -> io::Result<()> {
    replace_file(path, text)?;
    match path.parent() {
        Some(directory) => prune_records(directory),
        None => Ok(()),
    }
}
