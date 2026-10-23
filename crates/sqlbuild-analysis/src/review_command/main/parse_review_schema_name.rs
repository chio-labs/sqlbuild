//! The strict review schema name format.

use crate::review_command::constants::{
    SCHEMA_COMMIT_DIGITS, SCHEMA_RUN_DIGITS, SCHEMA_TIMESTAMP_LENGTH,
};

fn hex(text: &str, digits: usize) -> bool {
    text.len() == digits && text.bytes().all(|byte| byte.is_ascii_hexdigit())
}

/// The `YYYYMMDDTHHMMSSZ` creation time of a review schema name, or `None` for any other name.
#[must_use]
pub fn parse_review_schema_name(name: &str) -> Option<(i32, u32, u32, u32, u32, u32)> {
    let mut parts = name.rsplitn(4, '_');
    let run: &str = parts.next()?;
    let commit: &str = parts.next()?;
    let timestamp: &str = parts.next()?;
    let prefix: &str = parts.next()?;
    if prefix.is_empty() || !hex(run, SCHEMA_RUN_DIGITS) || !hex(commit, SCHEMA_COMMIT_DIGITS) {
        return None;
    }
    let upper: String = timestamp.to_ascii_uppercase();
    let bytes: &[u8] = upper.as_bytes();
    if bytes.len() != SCHEMA_TIMESTAMP_LENGTH || bytes[8] != b'T' || bytes[15] != b'Z' {
        return None;
    }
    let digits = |range: std::ops::Range<usize>| -> Option<u32> {
        let text: &str = upper.get(range)?;
        if !text.bytes().all(|byte| byte.is_ascii_digit()) {
            return None;
        }
        text.parse().ok()
    };
    let year: i32 = i32::try_from(digits(0..4)?).ok()?;
    let (month, day) = (digits(4..6)?, digits(6..8)?);
    let (hour, minute, second) = (digits(9..11)?, digits(11..13)?, digits(13..15)?);
    if !(1..=12).contains(&month)
        || !(1..=31).contains(&day)
        || hour > 23
        || minute > 59
        || second > 59
    {
        return None;
    }
    Some((year, month, day, hour, minute, second))
}
