//! Publish an incomplete capture before the command writes output, as `start_capture` does.

use std::io;

use crate::compute_logs::_helpers::files::{is_symlink, publish_staged, uuid4_hex};
use crate::compute_logs::_helpers::metadata::metadata_json;
use crate::compute_logs::_helpers::timestamps::{epoch_microseconds, utc_date};
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
    let streams = publish_staged(
        &staging,
        &directory,
        &metadata_json((&start, &invocation_id), None),
    )?;
    Ok(OpenCapture {
        start,
        invocation_id,
        directory,
        streams: Vec::from(streams),
    })
}
