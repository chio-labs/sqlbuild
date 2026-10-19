//! `observe_store_file`: which file a store path names and whether it is a SQLite database.

use std::io::ErrorKind;
use std::path::Path;

use crate::store::_helpers::identity::{file_identity, header_is_foreign};
use crate::store::models::StoreObservation;

/// The identity and header verdict of the file at `path`, read from one open handle; `None` when there is no file.
pub fn observe_store_file(path: &Path) -> std::io::Result<Option<StoreObservation>> {
    let file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    let identity = file_identity(&file.metadata()?);
    Ok(Some(StoreObservation {
        identity,
        header_foreign: header_is_foreign(&file),
    }))
}
