//! `pathlib` suffix handling on POSIX path text.

/// `PurePath.with_suffix(suffix)`: the last suffix of the final component replaced or added.
pub(crate) fn with_suffix(path: &str, suffix: &str) -> String {
    let start: usize = path.rfind('/').map_or(0, |index| index + 1);
    let name: &str = &path[start..];
    let stem_length: usize = match name.rfind('.') {
        Some(index) if index > 0 && index < name.len() - 1 => index,
        _ => name.len(),
    };
    format!("{}{}{suffix}", &path[..start], &name[..stem_length])
}

/// The first `max_bytes` bytes of `value`, without a trailing partial character.
pub(crate) fn truncate_utf8(value: &str, max_bytes: usize) -> &str {
    let mut end: usize = max_bytes.min(value.len());
    while !value.is_char_boundary(end) {
        end -= 1;
    }
    &value[..end]
}
