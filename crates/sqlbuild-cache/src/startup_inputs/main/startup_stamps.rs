//! Stamp every startup directory, its `.pth` files, the interpreter and its venv configuration.

use std::collections::BTreeSet;
use std::ffi::{OsStr, OsString};
use std::io;
use std::path::{Path, PathBuf};

use crate::startup_inputs::_helpers::pure_paths::{
    absolute, is_path_file, modified_ns, order_key, pure,
};
use crate::startup_inputs::constants::VENV_CONFIG;
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
            .map(|prefix| pure(prefix, &[OsStr::new(VENV_CONFIG)]).into_os_string()),
    );
    for directory in &directories {
        let directory: &Path = Path::new(directory);
        let Ok(listing) = std::fs::read_dir(directory) else {
            continue;
        };
        for entry in listing.flatten() {
            let name: OsString = entry.file_name();
            if is_path_file(&name) {
                paths.insert(pure(directory, &[name.as_os_str()]).into_os_string());
            }
        }
    }
    let mut ordered: Vec<PathBuf> = paths.into_iter().map(PathBuf::from).collect();
    ordered.sort_by_key(|path| order_key(path));
    ordered
        .into_iter()
        .map(|path| match std::fs::metadata(&path) {
            Ok(metadata) => match modified_ns(&metadata) {
                Ok(modified) => Ok(StartupStamp {
                    modified_ns: Some(modified),
                    size: Some(metadata.len()),
                    path,
                }),
                Err(error) => Err((path, error)),
            },
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(StartupStamp {
                path,
                modified_ns: None,
                size: None,
            }),
            Err(error) => Err((path, error)),
        })
        .collect()
}
