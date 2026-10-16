//! `PurePosixPath` reads of a project-relative path over its raw bytes.

use std::os::unix::ffi::OsStrExt;
use std::path::Path;

use crate::project_tree::constants::{
    CURRENT, DOUBLE_ROOT, ESCAPED_BYTE_BASE, PARENT, ROOT, SEPARATOR,
};

/// The components `PurePosixPath(path).parts` keeps after any root.
pub(crate) fn parts(path: &Path) -> Vec<&[u8]> {
    path.as_os_str()
        .as_bytes()
        .split(|byte| *byte == SEPARATOR)
        .filter(|part| !part.is_empty() && *part != CURRENT)
        .collect()
}

/// `PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts`.
pub(crate) fn escapes(path: &Path) -> bool {
    path.as_os_str().as_bytes().first() == Some(&SEPARATOR) || parts(path).contains(&PARENT)
}

/// `PurePosixPath(path).parts`: its root (`/` or exactly `//`) first, then each component.
pub(crate) fn rooted_parts(path: &Path) -> Vec<&[u8]> {
    let bytes: &[u8] = path.as_os_str().as_bytes();
    let mut rooted: Vec<&[u8]> = Vec::new();
    if bytes.starts_with(DOUBLE_ROOT) && bytes.get(DOUBLE_ROOT.len()) != Some(&SEPARATOR) {
        rooted.push(DOUBLE_ROOT);
    } else if bytes.first() == Some(&SEPARATOR) {
        rooted.push(ROOT);
    }
    rooted.extend(parts(path));
    rooted
}

/// Whether a part list starts with a root.
pub(crate) fn is_rooted(parts: &[&[u8]]) -> bool {
    parts
        .first()
        .is_some_and(|first| *first == ROOT || *first == DOUBLE_ROOT)
}

/// `str(PurePosixPath(*parts))` as bytes: the root, the components joined by `/`, or `.`.
pub(crate) fn joined_text(parts: &[&[u8]]) -> Vec<u8> {
    let (root, components): (&[u8], &[&[u8]]) = match parts.split_first() {
        Some((first, rest)) if *first == ROOT || *first == DOUBLE_ROOT => (first, rest),
        _ => (&[], parts),
    };
    if root.is_empty() && components.is_empty() {
        return CURRENT.to_vec();
    }
    let mut text: Vec<u8> = root.to_vec();
    text.extend(components.join(&SEPARATOR));
    text
}

/// `PurePosixPath(*parts).parent` as parts: a bare root or `.` is its own parent.
pub(crate) fn parent_parts<'a>(parts: &[&'a [u8]]) -> Vec<&'a [u8]> {
    match parts {
        [] => Vec::new(),
        [only] if is_rooted(&[only]) => vec![*only],
        [init @ .., _] => init.to_vec(),
    }
}

/// `PurePosixPath(*parts).relative_to(PurePosixPath(*base)).parts`, or `None` when not beneath.
pub(crate) fn relative_parts_to<'a>(parts: &[&'a [u8]], base: &[&[u8]]) -> Option<Vec<&'a [u8]>> {
    let beneath: bool = parts.len() >= base.len()
        && parts.iter().zip(base).all(|(part, prefix)| part == prefix)
        && !(base.is_empty() && is_rooted(parts));
    beneath.then(|| parts[base.len()..].to_vec())
}

/// Path bytes as text with one character per byte UTF-8 cannot decode, as `surrogateescape` reads.
pub(crate) fn escaped_text(bytes: &[u8]) -> String {
    let mut text: String = String::with_capacity(bytes.len());
    for chunk in bytes.utf8_chunks() {
        text.push_str(chunk.valid());
        text.extend(
            chunk
                .invalid()
                .iter()
                .filter_map(|byte| char::from_u32(ESCAPED_BYTE_BASE + u32::from(*byte))),
        );
    }
    text
}
