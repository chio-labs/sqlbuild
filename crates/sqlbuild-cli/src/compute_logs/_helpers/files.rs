//! Durable file steps of a capture: exclusive creation, atomic metadata and directory syncs.

use std::fs::{File, OpenOptions};
use std::io::{self, Write};
use std::path::Path;

use crate::compute_logs::constants::METADATA_FILE_NAME;

/// Random 128-bit hex text, as `uuid.uuid4().hex`.
pub(crate) fn uuid4_hex() -> io::Result<String> {
    let mut bytes = [0_u8; 16];
    getrandom::fill(&mut bytes).map_err(|error| io::Error::other(error.to_string()))?;
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

/// Open `path` for writing, failing when it exists, as Python's `open(path, "xb")`.
pub(crate) fn create_new(path: &Path) -> io::Result<File> {
    OpenOptions::new().write(true).create_new(true).open(path)
}

/// `os.fsync` of a directory, which Python opens read-only.
pub(crate) fn sync_directory(path: &Path) -> io::Result<()> {
    File::open(path)?.sync_all()
}

/// Write `metadata.json` through a synced temporary file replaced into place.
pub(crate) fn write_metadata(directory: &Path, json: &str) -> io::Result<()> {
    let temporary = directory.join(format!(".{METADATA_FILE_NAME}.{}.tmp", uuid4_hex()?));
    let result = write_and_replace(&temporary, &directory.join(METADATA_FILE_NAME), json)
        .and_then(|()| sync_directory(directory));
    if temporary.exists() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}

fn write_and_replace(temporary: &Path, destination: &Path, json: &str) -> io::Result<()> {
    let mut file = create_new(temporary)?;
    file.write_all(json.as_bytes())?;
    file.flush()?;
    file.sync_all()?;
    drop(file);
    std::fs::rename(temporary, destination)
}

/// Whether `path` is a symbolic link, without following it.
pub(crate) fn is_symlink(path: &Path) -> bool {
    std::fs::symlink_metadata(path).is_ok_and(|metadata| metadata.file_type().is_symlink())
}
