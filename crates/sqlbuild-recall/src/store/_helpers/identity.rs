//! File identity and SQLite header checks for moving a corrupt store aside.

use std::fs::{File, Metadata};
use std::io::Read;

use crate::store::constants::SQLITE_HEADER;
use crate::store::models::StoreFileIdentity;

#[cfg(unix)]
pub(crate) fn file_identity(metadata: &Metadata) -> StoreFileIdentity {
    use std::os::unix::fs::MetadataExt;
    StoreFileIdentity {
        volume: metadata.dev(),
        file: metadata.ino(),
    }
}

#[cfg(not(unix))]
pub(crate) fn file_identity(metadata: &Metadata) -> StoreFileIdentity {
    let modified: u64 = metadata.modified().map_or(0, |time| {
        time.duration_since(std::time::UNIX_EPOCH)
            .map_or(0, |elapsed| {
                u64::try_from(elapsed.as_nanos()).unwrap_or(u64::MAX)
            })
    });
    StoreFileIdentity {
        volume: metadata.len(),
        file: modified,
    }
}

/// Whether `file` has content that does not start with the SQLite header.
pub(crate) fn header_is_foreign(file: &File) -> bool {
    let mut header: Vec<u8> = Vec::with_capacity(SQLITE_HEADER.len());
    let read = file
        .take(SQLITE_HEADER.len() as u64)
        .read_to_end(&mut header);
    read.is_ok_and(|length| length > 0) && header.as_slice() != SQLITE_HEADER.as_slice()
}
