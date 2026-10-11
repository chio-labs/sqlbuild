//! The source files of an editable install, as Python's `os.scandir` walk lists them.

use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::digest::constants::{BYTECODE_CACHE_DIRECTORY, CODE_SOURCE_SUFFIXES};

/// Each source file's path below `root`, size and modification time in nanoseconds, sorted.
pub(crate) fn source_file_stats(root: &Path) -> Vec<(String, u64, i128)> {
    let mut stats: Vec<(String, u64, i128)> = Vec::new();
    let mut pending: Vec<PathBuf> = vec![root.to_path_buf()];
    while let Some(directory) = pending.pop() {
        let (directories, files): DirectoryListing = directory_stats(root, &directory);
        pending.extend(directories);
        stats.extend(files);
    }
    stats.sort();
    stats
}

/// A directory's subdirectories to walk and its source files' stats.
type DirectoryListing = (Vec<PathBuf>, Vec<(String, u64, i128)>);

/// One directory's subdirectories and source files; an error ends this directory's listing only.
fn directory_stats(root: &Path, directory: &Path) -> DirectoryListing {
    let mut listing: DirectoryListing = (Vec::new(), Vec::new());
    let _ = list_directory(root, directory, &mut listing);
    listing
}

/// Python's `os.scandir` walk of one directory, stopping at its first error.
fn list_directory(
    root: &Path,
    directory: &Path,
    listing: &mut DirectoryListing,
) -> std::io::Result<()> {
    let (pending, stats) = listing;
    for entry in std::fs::read_dir(directory)? {
        let entry: std::fs::DirEntry = entry?;
        let path: PathBuf = entry.path();
        if entry.file_type()?.is_dir() {
            if entry.file_name() != BYTECODE_CACHE_DIRECTORY {
                pending.push(path);
            }
            continue;
        }
        let source: bool = Path::new(&entry.file_name())
            .extension()
            .and_then(|suffix| suffix.to_str())
            .is_some_and(|suffix| CODE_SOURCE_SUFFIXES.contains(&suffix));
        if !source {
            continue;
        }
        let metadata: std::fs::Metadata = std::fs::metadata(&path)?;
        let relative: String = path
            .strip_prefix(root)
            .unwrap_or(&path)
            .to_string_lossy()
            .into_owned();
        stats.push((relative, metadata.len(), modified_nanoseconds(&metadata)?));
    }
    Ok(())
}

/// Python's `st_mtime_ns`: nanoseconds since the epoch, negative before it.
fn modified_nanoseconds(metadata: &std::fs::Metadata) -> std::io::Result<i128> {
    let modified: SystemTime = metadata.modified()?;
    Ok(match modified.duration_since(UNIX_EPOCH) {
        Ok(after) => i128::try_from(after.as_nanos()).unwrap_or(i128::MAX),
        Err(before) => -i128::try_from(before.duration().as_nanos()).unwrap_or(i128::MAX),
    })
}

/// Lowercase hexadecimal text of digest bytes, as Python's `hexdigest`.
pub(crate) fn lowercase_hex(bytes: &[u8]) -> String {
    bytes.iter().map(|byte| format!("{byte:02x}")).collect()
}
