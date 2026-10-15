//! `start_capture`: publish one incomplete capture and open its append streams.

use std::fs::File;
use std::path::Path;

use crate::compute_logs::_helpers::document::{encode_document, validate_document};
use crate::compute_logs::_helpers::files::{publish_staged, uuid4_hex};
use crate::compute_logs::_helpers::paths::{ensure_contained, ensure_not_symlink, find_capture};
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::models::CaptureDocument;

/// The open stdout, stderr and diagnostics files of the newly published capture.
pub fn publish_capture(
    root: &Path,
    document: &CaptureDocument,
) -> Result<[File; 3], ComputeLogError> {
    validate_document(document)?;
    let date_directory = root.join(&document.capture_date);
    ensure_not_symlink(&date_directory)?;
    std::fs::create_dir_all(&date_directory)?;
    ensure_not_symlink(&date_directory)?;
    ensure_contained(root, &date_directory)?;
    let directory = date_directory.join(&document.invocation_id);
    ensure_contained(root, &directory)?;
    if find_capture(root, &document.invocation_id)?.is_some() {
        return Err(ComputeLogError::rejected(
            ComputeLogErrorKind::AlreadyExists,
            format!(
                "capture already exists for invocation '{}'",
                document.invocation_id
            ),
        ));
    }
    let staging = date_directory.join(format!(".{}.{}.tmp", document.invocation_id, uuid4_hex()?));
    ensure_contained(root, &staging)?;
    std::fs::create_dir(&staging)?;
    Ok(publish_staged(
        &staging,
        &directory,
        &encode_document(document),
    )?)
}
