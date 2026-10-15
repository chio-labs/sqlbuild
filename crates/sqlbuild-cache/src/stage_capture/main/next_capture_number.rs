//! The sequence number of the next capture written into a capture directory.

/// Whether `name` is a numbered capture such as `001-discovery.json`.
fn numbered_capture(name: &str) -> bool {
    let Some((number, _)) = name.split_once('-') else {
        return false;
    };
    name.ends_with(".json")
        && !number.is_empty()
        && number.bytes().all(|byte| byte.is_ascii_digit())
}

/// One more than the numbered captures (`NNN-name.json`) among `file_names`.
#[must_use]
pub fn next_capture_number<'a>(file_names: impl IntoIterator<Item = &'a str>) -> u64 {
    let written: usize = file_names
        .into_iter()
        .filter(|name| numbered_capture(name))
        .count();
    u64::try_from(written).map_or(u64::MAX, |count| count.saturating_add(1))
}
