//! The strict review schema name format.

use crate::janitor_planning::models::ArchiveTimestamp;
use crate::review_command::constants::{
    LAST_DAY, LAST_HOUR, LAST_MINUTE, LAST_MONTH, LAST_SECOND, SCHEMA_COMMIT_DIGITS,
    SCHEMA_RUN_DIGITS, SCHEMA_TIMESTAMP_LENGTH,
};

fn hex(text: &str, digits: usize) -> bool {
    text.len() == digits && text.bytes().all(|byte| byte.is_ascii_hexdigit())
}

/// The decimal value of `bytes`, or `None` unless every byte is an ASCII digit.
fn decimal(bytes: &[u8]) -> Option<u32> {
    let mut value: u32 = 0;
    for byte in bytes {
        if !byte.is_ascii_digit() {
            return None;
        }
        value = value * 10 + u32::from(byte - b'0');
    }
    Some(value)
}

/// The `YYYYMMDDTHHMMSSZ` creation time of a review schema name, or `None` for any other name.
#[must_use]
pub fn parse_review_schema_name(name: &str) -> Option<ArchiveTimestamp> {
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
    let parsed = ArchiveTimestamp {
        year: decimal(&bytes[0..4])?,
        month: decimal(&bytes[4..6])?,
        day: decimal(&bytes[6..8])?,
        hour: decimal(&bytes[9..11])?,
        minute: decimal(&bytes[11..13])?,
        second: decimal(&bytes[13..15])?,
    };
    let valid: bool = (1..=LAST_MONTH).contains(&parsed.month)
        && (1..=LAST_DAY).contains(&parsed.day)
        && parsed.hour <= LAST_HOUR
        && parsed.minute <= LAST_MINUTE
        && parsed.second <= LAST_SECOND;
    valid.then_some(parsed)
}
