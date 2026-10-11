//! Publish an incomplete capture before the command writes output, as `start_capture` does.

use std::io::{self, Write};
use std::path::Path;

use crate::compute_logs::_helpers::files::{
    create_new, is_symlink, sync_directory, uuid4_hex, write_metadata,
};
use crate::compute_logs::_helpers::metadata::metadata_json;
use crate::compute_logs::_helpers::timestamps::{epoch_microseconds, utc_date};
use crate::compute_logs::constants::STREAM_FILE_NAMES;
use crate::compute_logs::models::{CaptureStart, OpenCapture};

/// The published capture, or the failure that leaves the command running without one.
pub fn start_capture(start: CaptureStart) -> io::Result<OpenCapture> {
    if is_symlink(&start.root) {
        return Err(io::Error::other(
            "configured compute log root cannot be a symlink",
        ));
    }
    std::fs::create_dir_all(&start.root)?;
    let date_directory = start
        .root
        .join(utc_date(epoch_microseconds(start.started_at)));
    if is_symlink(&date_directory) {
        return Err(io::Error::other("compute log path cannot be a symlink"));
    }
    std::fs::create_dir_all(&date_directory)?;
    let invocation_id = uuid4_hex()?;
    let directory = date_directory.join(&invocation_id);
    if directory.exists() || is_symlink(&directory) {
        return Err(io::Error::other("capture already exists"));
    }
    let staging = date_directory.join(format!(".{invocation_id}.{}.tmp", uuid4_hex()?));
    std::fs::create_dir(&staging)?;
    match published((&start, &invocation_id), &staging, &directory) {
        Ok(streams) => Ok(OpenCapture {
            start,
            invocation_id,
            directory,
            streams,
        }),
        Err(error) => {
            let _ = std::fs::remove_dir_all(&staging);
            let _ = std::fs::remove_dir_all(&directory);
            Err(error)
        }
    }
}

fn published(
    start: (&CaptureStart, &str),
    staging: &Path,
    directory: &Path,
) -> io::Result<Vec<std::fs::File>> {
    let mut streams: Vec<std::fs::File> = Vec::new();
    for name in STREAM_FILE_NAMES {
        streams.push(create_new(&staging.join(name))?);
    }
    write_metadata(staging, &metadata_json(start, None))?;
    for stream in &mut streams {
        stream.flush()?;
        stream.sync_all()?;
    }
    sync_directory(staging)?;
    std::fs::rename(staging, directory)?;
    if let Some(parent) = directory.parent() {
        sync_directory(parent)?;
    }
    Ok(streams)
}
