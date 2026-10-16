//! Stamp every startup directory, its `.pth` files, the interpreter and its venv configuration.

use std::collections::BTreeSet;
use std::ffi::OsString;
use std::io;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

use crate::startup_inputs::_helpers::pure_paths::{absolute, order_key, pure};
use crate::startup_inputs::constants::{PATH_FILE_SUFFIX, VENV_CONFIG};
use crate::startup_inputs::models::{StartupLocations, StartupStamp};

/// Sorted stamps of the startup paths; missing paths are unstamped and other stat failures fail.
pub fn startup_stamps(
    locations: &StartupLocations,
    cwd: &Path,
) -> Result<Vec<StartupStamp>, (PathBuf, io::Error)> {
    let directories: BTreeSet<OsString> = locations
        .directories
        .iter()
        .map(|directory| absolute(directory, cwd).into_os_string())
        .collect();
    let mut paths: BTreeSet<OsString> = directories.clone();
    paths.extend(
        locations
            .files
            .iter()
            .map(|file| pure(file, &[]).into_os_string()),
    );
    paths.extend(
        locations
            .prefixes
            .iter()
            .map(|prefix| pure(prefix, &[VENV_CONFIG]).into_os_string()),
    );
    for directory in &directories {
        let directory: &Path = Path::new(directory);
        let Ok(listing) = std::fs::read_dir(directory) else {
            continue;
        };
        for entry in listing.flatten() {
            if entry.file_name().as_bytes().ends_with(PATH_FILE_SUFFIX) {
                paths.insert(pure(directory, &[entry.file_name().as_bytes()]).into_os_string());
            }
        }
    }
    let mut ordered: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
    ordered.sort_by(|left, right| order_key(left).cmp(&order_key(right)));
    ordered
        .into_iter()
        .map(|path| match std::fs::metadata(&path) {
            Ok(metadata) => Ok(StartupStamp {
                modified_ns: Some(metadata.mtime() * 1_000_000_000 + metadata.mtime_nsec()),
                size: Some(metadata.len()),
                path,
            }),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(StartupStamp {
                path,
                modified_ns: None,
                size: None,
            }),
            Err(error) => Err((path, error)),
        })
        .collect()
}
