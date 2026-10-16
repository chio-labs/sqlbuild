//! `pathlib` reads of project paths: POSIX over raw bytes, Windows through the platform path rules.

use std::ffi::{OsStr, OsString};
use std::path::{MAIN_SEPARATOR, MAIN_SEPARATOR_STR, Path};

use crate::project_tree::constants::{CURRENT, PARENT, POSIX_SEPARATOR_BYTE};
use crate::project_tree::models::PureParts;

/// `PurePosixPath(path)`: its root (`/` or exactly `//`) and the components after it.
#[cfg(unix)]
pub(crate) fn pure_parts(path: &Path) -> PureParts {
    use std::os::unix::ffi::OsStrExt;

    let separator: u8 = POSIX_SEPARATOR_BYTE;
    let bytes: &[u8] = path.as_os_str().as_bytes();
    let anchor: &[u8] = match bytes {
        [first, second, rest @ ..]
            if *first == separator && *second == separator && rest.first() != Some(&separator) =>
        {
            &bytes[..2]
        }
        [first, ..] if *first == separator => &bytes[..1],
        _ => &[],
    };
    PureParts {
        anchor: OsStr::from_bytes(anchor).to_os_string(),
        tail: bytes
            .split(|byte| *byte == separator)
            .filter(|part| !part.is_empty() && *part != CURRENT.as_bytes())
            .map(|part| OsStr::from_bytes(part).to_os_string())
            .collect(),
    }
}

/// `PureWindowsPath(path)`: its drive and root with `\` separators, then each component.
#[cfg(not(unix))]
pub(crate) fn pure_parts(path: &Path) -> PureParts {
    use std::path::Component;

    use crate::project_tree::constants::POSIX_SEPARATOR;

    let mut parts: PureParts = PureParts {
        anchor: OsString::new(),
        tail: Vec::new(),
    };
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => parts.anchor.push(
                prefix
                    .as_os_str()
                    .to_string_lossy()
                    .replace(POSIX_SEPARATOR, MAIN_SEPARATOR_STR),
            ),
            Component::RootDir => parts.anchor.push(MAIN_SEPARATOR_STR),
            Component::CurDir => {}
            Component::ParentDir => parts.tail.push(OsString::from(PARENT)),
            Component::Normal(part) => parts.tail.push(part.to_os_string()),
        }
    }
    parts
}

/// Whether two parts are equal as `pathlib` compares them: exactly, or case-folded on Windows.
pub(crate) fn same_part(left: &OsStr, right: &OsStr) -> bool {
    if cfg!(unix) {
        left == right
    } else {
        left.to_string_lossy().to_lowercase() == right.to_string_lossy().to_lowercase()
    }
}

/// Whether `pathlib` considers two pure paths equal.
pub(crate) fn same_path(left: &PureParts, right: &PureParts) -> bool {
    same_part(&left.anchor, &right.anchor)
        && left.tail.len() == right.tail.len()
        && left
            .tail
            .iter()
            .zip(&right.tail)
            .all(|(left, right)| same_part(left, right))
}

/// `str(path)`: the anchor, then the components joined by the platform separator, or `.`.
pub(crate) fn pure_text(parts: &PureParts) -> OsString {
    if parts.anchor.is_empty() && parts.tail.is_empty() {
        return OsString::from(CURRENT);
    }
    let mut text: OsString = parts.anchor.clone();
    for (index, part) in parts.tail.iter().enumerate() {
        if index > 0 {
            text.push(MAIN_SEPARATOR_STR);
        }
        text.push(part);
    }
    text
}

/// `path.as_posix()` as encoded bytes.
pub(crate) fn posix_bytes(parts: &PureParts) -> Vec<u8> {
    pure_text(parts)
        .as_encoded_bytes()
        .iter()
        .map(|byte| {
            if char::from(*byte) == MAIN_SEPARATOR {
                POSIX_SEPARATOR_BYTE
            } else {
                *byte
            }
        })
        .collect()
}

/// `path.parent`: a bare anchor or `.` is its own parent.
pub(crate) fn pure_parent(parts: &PureParts) -> PureParts {
    let mut parent: PureParts = parts.clone();
    parent.tail.pop();
    parent
}

/// `path.relative_to(base)`, or `None` when `path` is not beneath `base`.
pub(crate) fn pure_relative_to(parts: &PureParts, base: &PureParts) -> Option<PureParts> {
    let beneath: bool = same_part(&parts.anchor, &base.anchor)
        && parts.tail.len() >= base.tail.len()
        && parts
            .tail
            .iter()
            .zip(&base.tail)
            .all(|(part, prefix)| same_part(part, prefix));
    beneath.then(|| PureParts {
        anchor: OsString::new(),
        tail: parts.tail[base.tail.len()..].to_vec(),
    })
}

/// `path.parts`: the anchor, when there is one, then each component.
pub(crate) fn part_list(parts: PureParts) -> Vec<OsString> {
    let anchor: Option<OsString> = (!parts.anchor.is_empty()).then_some(parts.anchor);
    anchor.into_iter().chain(parts.tail).collect()
}

/// `path.is_absolute() or ".." in path.parts`.
pub(crate) fn escapes(path: &Path) -> bool {
    path.is_absolute() || pure_parts(path).tail.iter().any(|part| part == PARENT)
}

/// Path text with one private-use character per undecodable byte, as `surrogateescape` reads.
#[cfg(unix)]
pub(crate) fn escaped_text(path: &Path) -> String {
    use std::os::unix::ffi::OsStrExt;

    use crate::project_tree::constants::ESCAPED_BASE;

    let mut text: String = String::new();
    for chunk in path.as_os_str().as_bytes().utf8_chunks() {
        text.push_str(chunk.valid());
        text.extend(
            chunk
                .invalid()
                .iter()
                .filter_map(|byte| char::from_u32(ESCAPED_BASE + u32::from(*byte))),
        );
    }
    text
}

/// Path text with one private-use character per unpaired surrogate, as Python keeps them.
#[cfg(windows)]
pub(crate) fn escaped_text(path: &Path) -> String {
    use std::os::windows::ffi::OsStrExt;

    use crate::project_tree::constants::ESCAPED_BASE;

    char::decode_utf16(path.as_os_str().encode_wide())
        .filter_map(|decoded| match decoded {
            Ok(character) => Some(character),
            Err(error) => char::from_u32(ESCAPED_BASE + u32::from(error.unpaired_surrogate())),
        })
        .collect()
}
