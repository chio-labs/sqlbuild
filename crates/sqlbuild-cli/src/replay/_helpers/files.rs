//! Atomic launch record writes and pruning of the oldest records.

use std::fs;
use std::io;
use std::path::{Path, PathBuf};

use crate::replay::constants::{LAUNCH_RECORD_LIMIT, LAUNCH_RECORD_SUFFIX};

/// 32 random hex digits, as Python's `uuid.uuid4().hex`.
fn uuid4_hex() -> io::Result<String> {
    let mut bytes = [0_u8; 16];
    getrandom::fill(&mut bytes).map_err(|error| io::Error::other(error.to_string()))?;
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

/// Write `text` to `path` through a hidden temporary sibling replaced into place.
pub(crate) fn replace_file(path: &Path, text: &str) -> io::Result<()> {
    let Some(parent) = path.parent() else {
        return Err(io::Error::other("a launch record path has no directory"));
    };
    fs::create_dir_all(parent)?;
    let name: String = path
        .file_name()
        .map(|name| name.to_string_lossy().into_owned())
        .unwrap_or_default();
    let temporary: PathBuf = path.with_file_name(format!(".{name}.{}.tmp", uuid4_hex()?));
    let written: io::Result<()> =
        fs::write(&temporary, text.as_bytes()).and_then(|()| fs::rename(&temporary, path));
    let _ = fs::remove_file(&temporary);
    written
}

/// Delete all but the newest `LAUNCH_RECORD_LIMIT` records in `directory`.
pub(crate) fn prune_records(directory: &Path) -> io::Result<()> {
    let mut records: Vec<(i128, String, PathBuf)> = Vec::new();
    for entry in fs::read_dir(directory)? {
        let entry: fs::DirEntry = entry?;
        let name: String = entry.file_name().to_string_lossy().into_owned();
        if !name.ends_with(LAUNCH_RECORD_SUFFIX) {
            continue;
        }
        let metadata: fs::Metadata = fs::metadata(entry.path())?;
        records.push((modified_ns(&metadata)?, name, entry.path()));
    }
    records.sort_by(|left, right| right.cmp(left));
    for (_, _, stale) in records.into_iter().skip(LAUNCH_RECORD_LIMIT) {
        let _ = fs::remove_file(stale);
    }
    Ok(())
}

/// `os.stat(path).st_mtime_ns`.
fn modified_ns(metadata: &fs::Metadata) -> io::Result<i128> {
    let modified: std::time::SystemTime = metadata.modified()?;
    Ok(match modified.duration_since(std::time::UNIX_EPOCH) {
        Ok(after) => i128::try_from(after.as_nanos()).unwrap_or(i128::MAX),
        Err(before) => -i128::try_from(before.duration().as_nanos()).unwrap_or(i128::MAX),
    })
}
