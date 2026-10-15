//! The strict janitor archive name grammar.

use crate::janitor_planning::_helpers::name_parts::{
    after_marker, leading_number, strip_prefix_folded,
};
use crate::janitor_planning::constants::{
    ARCHIVE_NAME_PREFIX, ARCHIVE_NAME_SEPARATOR, DATE_DIGITS, LAST_HOUR, LAST_MINUTE, LAST_MONTH,
    LAST_SECOND, TIME_DIGITS, YEAR_DIGITS,
};
use crate::janitor_planning::models::{ArchiveTimestamp, ParsedArchiveName};

/// The archive timestamp and logical name, or `None` for anything outside the strict grammar.
#[must_use]
pub fn parse_archive_name(name: &str) -> Option<ParsedArchiveName> {
    let rest: &str = strip_prefix_folded(name, ARCHIVE_NAME_PREFIX)?;
    let (year, rest) = leading_number(rest, YEAR_DIGITS)?;
    let (month, rest) = leading_number(rest, DATE_DIGITS)?;
    let (day, rest) = leading_number(rest, DATE_DIGITS)?;
    let rest: &str = after_marker(rest, 'T')?;
    let (hour, rest) = leading_number(rest, TIME_DIGITS)?;
    let (minute, rest) = leading_number(rest, TIME_DIGITS)?;
    let (second, rest) = leading_number(rest, TIME_DIGITS)?;
    let rest: &str = after_marker(rest, 'Z')?;
    let logical_name: &str = rest.strip_prefix(ARCHIVE_NAME_SEPARATOR)?;
    if logical_name.is_empty() || logical_name.contains('\n') {
        return None;
    }
    let archived_at = ArchiveTimestamp {
        year,
        month,
        day,
        hour,
        minute,
        second,
    };
    valid(archived_at).then(|| ParsedArchiveName {
        archived_at,
        logical_name: logical_name.to_owned(),
    })
}

fn valid(value: ArchiveTimestamp) -> bool {
    value.year >= 1
        && (1..=LAST_MONTH).contains(&value.month)
        && value.day >= 1
        && value.day <= days_in_month(value.year, value.month)
        && value.hour <= LAST_HOUR
        && value.minute <= LAST_MINUTE
        && value.second <= LAST_SECOND
}

fn days_in_month(year: u32, month: u32) -> u32 {
    let leap: bool =
        year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    match month {
        2 if leap => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}
