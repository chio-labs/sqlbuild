//! `get_metadata`: the published metadata of one capture, validated against its directory.

use std::path::{Path, PathBuf};

use crate::compute_logs::_helpers::document::{decode_document, validate_document};
use crate::compute_logs::_helpers::paths::{ensure_contained, existing_capture};
use crate::compute_logs::_helpers::stored::validate_directory_document;
use crate::compute_logs::constants::METADATA_FILE_NAME;
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::models::CaptureDocument;

/// The capture's document and directory; read failures become metadata errors.
pub fn read_capture_document(
    root: &Path,
    invocation_id: &str,
) -> Result<(CaptureDocument, PathBuf), ComputeLogError> {
    let directory = existing_capture(root, invocation_id)?;
    let path = directory.join(METADATA_FILE_NAME);
    ensure_contained(root, &path)?;
    let raw = std::fs::read_to_string(&path).map_err(|error| {
        ComputeLogError::rejected(
            ComputeLogErrorKind::Metadata,
            format!("unable to read capture metadata: {error}"),
        )
    })?;
    let document = decode_document(&raw)?;
    validate_document(&document)?;
    validate_directory_document(&directory, &document)?;
    Ok((document, directory))
}
