//! Python's code segment bounds and statement terminator characters.

/// Python's `" \t\r\n\f\v;"`.
pub(crate) fn is_terminator(byte: u8) -> bool {
    matches!(byte, b' ' | b'\t' | b'\r' | b'\n' | 0x0c | 0x0b | b';')
}

/// `sql` without trailing terminator characters.
pub(crate) fn trimmed_end(sql: &[u8], start: usize, end: usize) -> usize {
    let mut index: usize = end;
    while index > start && is_terminator(sql[index - 1]) {
        index -= 1;
    }
    index
}

/// The first and last code bytes so far, extended by the code segment `start..end`.
pub(crate) fn segment_bounds(
    sql: &[u8],
    start: usize,
    end: usize,
    bounds: Option<(usize, usize)>,
) -> Option<(usize, usize)> {
    let stripped_end: usize = trimmed_end(sql, start, end);
    let leading: usize = sql[start..stripped_end]
        .iter()
        .position(|byte| !is_terminator(*byte))?;
    let first: usize = bounds.map_or(start + leading, |(first, _)| first);
    Some((first, stripped_end - 1))
}

/// Python's `_may_end_with_comment` over the body without trailing terminators.
pub(crate) fn may_end_with_comment(tail: &[u8], prefixes: &[String]) -> bool {
    let line_start: usize = tail
        .iter()
        .rposition(|byte| *byte == b'\n')
        .map_or(0, |index| index + 1);
    let last_line: &[u8] = &tail[line_start..];
    if tail.ends_with(b"*/") {
        return true;
    }
    for prefix in prefixes {
        if last_line
            .windows(prefix.len())
            .any(|window| window == prefix.as_bytes())
        {
            return true;
        }
    }
    false
}
