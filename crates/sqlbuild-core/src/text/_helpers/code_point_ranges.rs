//! Membership in the generated, ordered code point range tables.

/// Whether one character falls inside the inclusive, ordered code point `ranges`.
pub(crate) fn in_ranges(ranges: &[(u32, u32)], character: char) -> bool {
    let code_point: u32 = u32::from(character);
    let index: usize = ranges.partition_point(|(_, end)| *end < code_point);
    ranges
        .get(index)
        .is_some_and(|(start, _)| *start <= code_point)
}
