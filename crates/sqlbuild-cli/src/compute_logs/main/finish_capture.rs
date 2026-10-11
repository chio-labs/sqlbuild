//! Append a command's output, publish its final metadata and prune, as Python's finalize does.

use std::io::{self, Write};
use std::time::SystemTime;

use crate::compute_logs::_helpers::files::{create_new, sync_directory, write_metadata};
use crate::compute_logs::_helpers::metadata::metadata_json;
use crate::compute_logs::_helpers::prune::prune;
use crate::compute_logs::_helpers::timestamps::epoch_microseconds;
use crate::compute_logs::constants::{COMPLETE_FILE_NAME, DEFAULT_RETENTION_COUNT};
use crate::compute_logs::models::{CaptureEnd, OpenCapture};

/// Complete the capture; a failure leaves it incomplete, as Python's best-effort capture does.
pub fn finish_capture(capture: OpenCapture, end: &CaptureEnd) -> io::Result<()> {
    let OpenCapture {
        start,
        invocation_id,
        directory,
        mut streams,
    } = capture;
    let [stdout, stderr, diagnostics] = streams.as_mut_slice() else {
        return Err(io::Error::other("capture streams are not open"));
    };
    stdout.write_all(&end.stdout)?;
    stderr.write_all(&end.stderr)?;
    for stream in [&mut *stdout, &mut *stderr, &mut *diagnostics] {
        stream.flush()?;
        stream.sync_all()?;
    }
    drop(streams);
    write_metadata(
        &directory,
        &metadata_json(
            (&start, &invocation_id),
            Some((
                end,
                epoch_microseconds(SystemTime::now()),
                (end.stdout.len(), end.stderr.len(), 0),
            )),
        ),
    )?;
    create_new(&directory.join(COMPLETE_FILE_NAME))?.sync_all()?;
    sync_directory(&directory)?;
    prune(&start.root, DEFAULT_RETENTION_COUNT);
    Ok(())
}
