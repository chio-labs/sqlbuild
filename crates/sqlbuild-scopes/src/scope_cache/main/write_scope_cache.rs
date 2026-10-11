//! `write_cached_scope_index`'s atomic replace, ignoring I/O faults.

use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

/// Write `envelope` to `directory/file_name` through a synced temporary file.
pub fn write_scope_cache(directory: &Path, file_name: &str, envelope: &[u8]) -> io::Result<()> {
    std::fs::create_dir_all(directory)?;
    let nonce: u128 = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |elapsed| elapsed.as_nanos());
    let temporary: PathBuf =
        directory.join(format!(".scope-index-{}-{nonce:x}", std::process::id()));
    let written: io::Result<()> = std::fs::File::create_new(&temporary)
        .and_then(|mut stream| {
            stream.write_all(envelope)?;
            stream.flush()?;
            stream.sync_all()
        })
        .and_then(|()| std::fs::rename(&temporary, directory.join(file_name)));
    if written.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    written
}
