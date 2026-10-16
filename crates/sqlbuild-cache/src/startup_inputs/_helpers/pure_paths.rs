//! `pathlib.PurePosixPath` spelling and ordering over raw path bytes.

use std::ffi::OsString;
use std::os::unix::ffi::{OsStrExt, OsStringExt};
use std::path::{Path, PathBuf};

use crate::startup_inputs::constants::{CURRENT, SEPARATOR};

/// The root a POSIX path keeps: two leading slashes stay two, more collapse to one.
fn root(bytes: &[u8]) -> &[u8] {
    match bytes {
        [SEPARATOR, SEPARATOR, rest @ ..] if rest.first() != Some(&SEPARATOR) => &bytes[..2],
        [SEPARATOR, ..] => &bytes[..1],
        _ => &[],
    }
}

/// `str(PurePosixPath(path, *children))`.
pub(crate) fn pure(path: &Path, children: &[&[u8]]) -> PathBuf {
    let bytes: &[u8] = path.as_os_str().as_bytes();
    let mut text: Vec<u8> = root(bytes).to_vec();
    let parts = std::iter::once(bytes)
        .chain(children.iter().copied())
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
    PathBuf::from(OsString::from_vec(text))
}

/// `str(Path(path).absolute())` against the working directory `cwd`.
pub(crate) fn absolute(path: &Path, cwd: &Path) -> PathBuf {
    if root(path.as_os_str().as_bytes()).is_empty() {
        pure(cwd, &[path.as_os_str().as_bytes()])
    } else {
        pure(path, &[])
    }
}

/// The `/`-separated parts `PurePosixPath` orders paths by.
pub(crate) fn order_key(path: &Path) -> Vec<&[u8]> {
    path.as_os_str()
        .as_bytes()
        .split(|byte| *byte == SEPARATOR)
        .collect()
}
