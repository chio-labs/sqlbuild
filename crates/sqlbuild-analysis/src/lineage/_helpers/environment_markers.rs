//! Python's `ENV:\s*([A-Za-z0-9_]+)` scan over bytes, with its cacheability checks.

use crate::lineage::constants::ENVIRONMENT_MARKER;

/// The environment names `contents` reads, or `None` where Python refuses to cache the graph:
/// a marker without a name, or a name directly followed by a non-ASCII byte.
pub(crate) fn environment_names(contents: &[u8]) -> Option<Vec<&str>> {
    let mut names: Vec<&str> = Vec::new();
    for start in marker_positions(contents, true) {
        let Some(end) = match_end(contents, start) else {
            continue;
        };
        if contents.get(end).is_some_and(|byte| *byte >= 128) {
            return None;
        }
        let name = &contents[start + ENVIRONMENT_MARKER.len()..end];
        names.push(std::str::from_utf8(name).ok()?.trim_start_matches(is_python_space_char));
    }
    (names.len() == marker_positions(contents, false).len()).then_some(names)
}

fn is_python_space_char(character: char) -> bool {
    u8::try_from(character).is_ok_and(|byte| is_python_bytes_space(&byte))
}

/// Non-overlapping marker starts (`bytes.count`); `matching` skips past each regex match instead.
fn marker_positions(contents: &[u8], matching: bool) -> Vec<usize> {
    let mut positions: Vec<usize> = Vec::new();
    let mut position = 0;
    while let Some(offset) = find(&contents[position..], ENVIRONMENT_MARKER) {
        let start = position + offset;
        positions.push(start);
        position = if matching {
            match_end(contents, start).unwrap_or(start + 1)
        } else {
            start + ENVIRONMENT_MARKER.len()
        };
    }
    positions
}

/// Where a regex match starting at `start` ends, if it matches.
fn match_end(contents: &[u8], start: usize) -> Option<usize> {
    let mut position = start + ENVIRONMENT_MARKER.len();
    while contents.get(position).is_some_and(is_python_bytes_space) {
        position += 1;
    }
    let name_start = position;
    while contents.get(position).is_some_and(is_name_byte) {
        position += 1;
    }
    (position > name_start).then_some(position)
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

/// Python's bytes-pattern `\s`: ASCII space, tab, newline, return, vertical tab and form feed.
fn is_python_bytes_space(byte: &u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

fn is_name_byte(byte: &u8) -> bool {
    byte.is_ascii_alphanumeric() || *byte == b'_'
}
