//! `datetime.fromisoformat` for the timestamps integration records carry.

use crate::integration_results::constants::{MAX_DAY, MAX_HOUR, MAX_MINUTE_OR_SECOND, MAX_MONTH};

fn digits(text: &[u8], count: usize) -> Option<(u32, &[u8])> {
    if text.len() < count || !text[..count].iter().all(u8::is_ascii_digit) {
        return None;
    }
    let value: u32 = text[..count]
        .iter()
        .fold(0, |total, digit| total * 10 + u32::from(digit - b'0'));
    Some((value, &text[count..]))
}

/// `HH[:MM[:SS[.ffffff]]]` of a time or offset, returning the rest.
fn clock(text: &[u8]) -> Option<&[u8]> {
    let (hour, mut rest) = digits(text, 2)?;
    if hour > MAX_HOUR {
        return None;
    }
    for limit in [MAX_MINUTE_OR_SECOND, MAX_MINUTE_OR_SECOND] {
        let Some(after) = rest.strip_prefix(b":") else {
            break;
        };
        let (value, after) = digits(after, 2)?;
        if value > limit {
            return None;
        }
        rest = after;
    }
    if let Some(after) = rest.strip_prefix(b".").or_else(|| rest.strip_prefix(b",")) {
        let length: usize = after
            .iter()
            .take_while(|byte| byte.is_ascii_digit())
            .count();
        if length == 0 {
            return None;
        }
        rest = &after[length..];
    }
    Some(rest)
}

/// Whether the text is an ISO 8601 date-time `fromisoformat` reads with a UTC offset.
pub(crate) fn aware_timestamp(text: &str) -> Option<bool> {
    let bytes: &[u8] = text.as_bytes();
    let (_, rest) = digits(bytes, 4)?;
    let rest: &[u8] = rest.strip_prefix(b"-")?;
    let (month, rest) = digits(rest, 2)?;
    let rest: &[u8] = rest.strip_prefix(b"-")?;
    let (day, rest) = digits(rest, 2)?;
    if !(1..=MAX_MONTH).contains(&month) || !(1..=MAX_DAY).contains(&day) {
        return None;
    }
    if rest.is_empty() {
        return Some(false);
    }
    let rest: &[u8] = clock(&rest[1..])?;
    if rest.is_empty() {
        return Some(false);
    }
    if rest == b"Z" {
        return Some(true);
    }
    let offset: &[u8] = rest
        .strip_prefix(b"+")
        .or_else(|| rest.strip_prefix(b"-"))?;
    clock(offset)?.is_empty().then_some(true)
}
