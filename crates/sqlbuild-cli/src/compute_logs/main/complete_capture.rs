//! `mark_complete`: close a checked capture's streams and publish its final metadata and marker.

use std::fs::File;
use std::path::Path;

use crate::compute_logs::_helpers::document::encode_document;
use crate::compute_logs::_helpers::files::{create_new, sync_directory, write_metadata};
use crate::compute_logs::constants::COMPLETE_FILE_NAME;
use crate::compute_logs::errors::ComputeLogError;
use crate::compute_logs::models::CaptureDocument;

/// Close the already synced `streams`, then publish the final metadata and completion marker.
pub fn complete_capture(
    directory: &Path,
    document: &CaptureDocument,
    streams: [File; 3],
) -> Result<(), ComputeLogError> {
    drop(streams);
    write_metadata(directory, &encode_document(document))?;
    create_new(&directory.join(COMPLETE_FILE_NAME))?.sync_all()?;
    sync_directory(directory)?;
    Ok(())
}
