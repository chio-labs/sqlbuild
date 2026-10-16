//! `pathlib` spelling, ordering and stat reads for startup stamps on each platform.

use std::ffi::OsStr;
use std::fs::Metadata;
use std::path::{Path, PathBuf};

use crate::startup_inputs::constants::PATH_FILE_SUFFIX;
#[cfg(unix)]
use crate::startup_inputs::constants::{CURRENT, SEPARATOR};

/// The root a POSIX path keeps: two leading slashes stay two, more collapse to one.
#[cfg(unix)]
fn root(bytes: &[u8]) -> &[u8] {
    match bytes {
        [SEPARATOR, SEPARATOR, rest @ ..] if rest.first() != Some(&SEPARATOR) => &bytes[..2],
        [SEPARATOR, ..] => &bytes[..1],
        _ => &[],
    }
}

/// `str(PurePosixPath(path, *children))`.
#[cfg(unix)]
pub(crate) fn pure(path: &Path, children: &[&OsStr]) -> PathBuf {
    use std::os::unix::ffi::{OsStrExt, OsStringExt};

    let bytes: &[u8] = path.as_os_str().as_bytes();
    let mut text: Vec<u8> = root(bytes).to_vec();
    let parts = std::iter::once(bytes)
        .chain(children.iter().map(|child| child.as_bytes()))
        .flat_map(|segment| segment.split(|byte| *byte == SEPARATOR))
        .filter(|part| !part.is_empty() && *part != CURRENT);
    let mut first: bool = true;
    for part in parts {
        if !first {
            text.push(SEPARATOR);
        }
        text.extend_from_slice(part);
        first = false;
    }
    if text.is_empty() {
        text.extend_from_slice(CURRENT);
    }
    PathBuf::from(std::ffi::OsString::from_vec(text))
}

/// `str(PureWindowsPath(path, *children))` through the platform path rules.
#[cfg(not(unix))]
pub(crate) fn pure(path: &Path, children: &[&OsStr]) -> PathBuf {
    let mut joined: PathBuf = path.components().collect();
    for child in children {
        joined.push(child);
    }
    joined
}

/// `str(Path(path).absolute())` against the working directory `cwd`.
pub(crate) fn absolute(path: &Path, cwd: &Path) -> PathBuf {
    if path.has_root() && (cfg!(unix) || path.is_absolute()) {
        pure(path, &[])
    } else {
        pure(cwd, &[path.as_os_str()])
    }
}

/// The `/`-separated parts `PurePosixPath` orders paths by.
#[cfg(unix)]
pub(crate) fn order_key(path: &Path) -> Vec<Vec<u8>> {
    use std::os::unix::ffi::OsStrExt;

    path.as_os_str()
        .as_bytes()
        .split(|byte| *byte == SEPARATOR)
        .map(<[u8]>::to_vec)
        .collect()
}

/// The case-folded parts `PureWindowsPath` orders paths by.
#[cfg(not(unix))]
pub(crate) fn order_key(path: &Path) -> Vec<Vec<u8>> {
    path.components()
        .map(|part| {
            part.as_os_str()
                .to_string_lossy()
                .to_lowercase()
                .into_bytes()
        })
        .collect()
}

/// Whether `glob("*.pth")` matches a directory entry name on this platform.
pub(crate) fn is_path_file(name: &OsStr) -> bool {
    if cfg!(unix) {
        name.as_encoded_bytes().ends_with(PATH_FILE_SUFFIX)
    } else {
        name.to_string_lossy()
            .to_lowercase()
            .as_bytes()
            .ends_with(PATH_FILE_SUFFIX)
    }
}

/// `os.stat(path).st_mtime_ns`.
#[cfg(unix)]
pub(crate) fn modified_ns(metadata: &Metadata) -> std::io::Result<i64> {
    use std::os::unix::fs::MetadataExt;

    Ok(metadata.mtime() * 1_000_000_000 + metadata.mtime_nsec())
}

/// `os.stat(path).st_mtime_ns` from the platform modification time, negative before 1970.
#[cfg(not(unix))]
pub(crate) fn modified_ns(metadata: &Metadata) -> std::io::Result<i64> {
    let modified: std::time::SystemTime = metadata.modified()?;
    let (nanos, sign): (u128, i64) = match modified.duration_since(std::time::UNIX_EPOCH) {
        Ok(elapsed) => (elapsed.as_nanos(), 1),
        Err(before) => (before.duration().as_nanos(), -1),
    };
    i64::try_from(nanos)
        .map(|value| sign * value)
        .map_err(std::io::Error::other)
}
