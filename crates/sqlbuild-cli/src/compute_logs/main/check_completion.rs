//! `mark_complete`: check final metadata against the capture before publishing it.

use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::document::validate_document;
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::main::read_capture_document::read_capture_document;
use crate::compute_logs::models::CaptureDocument;

fn metadata_error(message: &str) -> ComputeLogError {
    ComputeLogError::rejected(ComputeLogErrorKind::Metadata, message)
}

/// The capture directory once `document` matches its start and the open streams' `counts`.
pub fn check_completion(
    root: &Path,
    document: &CaptureDocument,
    counts: Option<[i64; 3]>,
) -> Result<PathBuf, ComputeLogError> {
    validate_document(document)?;
    let Some(counts) = counts else {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::State,
            "capture is not active in this storage instance",
        ));
    };
    let mismatch = || metadata_error("final metadata does not match capture start metadata");
    let completion = document.completion.as_ref().ok_or_else(mismatch)?;
    let (initial, directory) = read_capture_document(root, &document.invocation_id)?;
    let same_start = (
        initial.started_at.micros,
        &initial.capture_date,
        &initial.command,
        &initial.project_dir,
        &initial.target,
        &initial.run_id,
    ) == (
        document.started_at.micros,
        &document.capture_date,
        &document.command,
        &document.project_dir,
        &document.target,
        &document.run_id,
    );
    if initial.completion.is_some() || !same_start {
        return Err(mismatch());
    }
    let expected = [
        completion.stdout_bytes,
        completion.stderr_bytes,
        completion.diagnostics_bytes,
    ];
    if counts != expected {
        return Err(metadata_error(
            "final byte counts do not match captured streams",
        ));
    }
    Ok(directory)
}
