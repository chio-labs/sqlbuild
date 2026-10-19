//! `store_header_is_foreign`: whether a store file holds something other than a SQLite database.

use std::io::Read;
use std::path::Path;

use crate::store::constants::SQLITE_HEADER;

/// Whether `path` exists with content that is not a SQLite database; never opens it with SQLite.
#[must_use]
pub fn store_header_is_foreign(path: &Path) -> bool {
    let mut header: Vec<u8> = Vec::with_capacity(SQLITE_HEADER.len());
    let read = std::fs::File::open(path).and_then(|file| {
        file.take(SQLITE_HEADER.len() as u64)
            .read_to_end(&mut header)
    });
    read.is_ok_and(|length| length > 0) && header.as_slice() != SQLITE_HEADER.as_slice()
}
