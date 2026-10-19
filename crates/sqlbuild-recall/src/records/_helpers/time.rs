//! UTC timestamps as Recall stores them: `YYYY-MM-DDTHH:MM:SS.ffffffZ`.

use std::time::{SystemTime, UNIX_EPOCH};

use crate::records::constants::{
    DECIMAL_RADIX, FEBRUARY, MARCH_BASED_JANUARY_INDEX, MICROS_PER_SECOND, SECONDS_PER_DAY,
};

/// Days since 1970-01-01 of a proleptic Gregorian date.
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let year = if month <= FEBRUARY { year - 1 } else { year };
    let era = year.div_euclid(400);
    let year_of_era = year - era * 400;
    let month_index = (month + 9) % 12;
    let day_of_year = (153 * month_index + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - 719_468
}

/// The date of a day count since 1970-01-01.
fn civil_from_days(days: i64) -> (i64, i64, i64) {
    let shifted = days + 719_468;
    let era = shifted.div_euclid(146_097);
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = if month_index < MARCH_BASED_JANUARY_INDEX {
        month_index + 3
    } else {
        month_index - 9
    };
    let year = year_of_era + era * 400 + i64::from(month <= FEBRUARY);
    (year, month, day)
}

/// Microseconds since the epoch as a stored timestamp.
pub(crate) fn format_micros(micros: i64) -> String {
    let seconds = micros.div_euclid(MICROS_PER_SECOND);
    let fraction = micros.rem_euclid(MICROS_PER_SECOND);
    let days = seconds.div_euclid(SECONDS_PER_DAY);
    let second_of_day = seconds.rem_euclid(SECONDS_PER_DAY);
    let (year, month, day) = civil_from_days(days);
    format!(
        "{year:04}-{month:02}-{day:02}T{:02}:{:02}:{:02}.{fraction:06}Z",
        second_of_day / 3600,
        second_of_day % 3600 / 60,
        second_of_day % 60
    )
}

/// Microseconds since the epoch of a system time.
pub(crate) fn system_micros(time: SystemTime) -> i64 {
    match time.duration_since(UNIX_EPOCH) {
        Ok(elapsed) => i64::try_from(elapsed.as_micros()).unwrap_or(i64::MAX),
        Err(before) => -i64::try_from(before.duration().as_micros()).unwrap_or(i64::MAX),
    }
}

fn digits(text: &str) -> Option<i64> {
    if text.is_empty() {
        return None;
    }
    text.bytes().try_fold(0_i64, |total, byte| {
        let digit = char::from(byte).to_digit(DECIMAL_RADIX)?;
        total
            .checked_mul(i64::from(DECIMAL_RADIX))?
            .checked_add(i64::from(digit))
    })
}

/// Microseconds since the epoch of an ISO-8601 timestamp in UTC (`Z` or `+00:00`) or naive UTC.
pub(crate) fn parse_micros(text: &str) -> Option<i64> {
    let text = text
        .strip_suffix('Z')
        .or_else(|| text.strip_suffix("+00:00"))
        .unwrap_or(text);
    let (date, time) = text.split_once(['T', ' '])?;
    let mut date_parts = date.split('-');
    let year = digits(date_parts.next()?)?;
    let month = digits(date_parts.next()?)?;
    let day = digits(date_parts.next()?)?;
    let (clock, fraction) = time.split_once('.').unwrap_or((time, ""));
    let mut clock_parts = clock.split(':');
    let hour = digits(clock_parts.next()?)?;
    let minute = digits(clock_parts.next()?)?;
    let second = digits(clock_parts.next()?)?;
    if date_parts.next().is_some() || clock_parts.next().is_some() {
        return None;
    }
    let micros = if fraction.is_empty() {
        0
    } else {
        let padded: String = fraction.chars().chain("000000".chars()).take(6).collect();
        digits(&padded)?
    };
    let days = days_from_civil(year, month, day);
    Some((days * SECONDS_PER_DAY + hour * 3600 + minute * 60 + second) * MICROS_PER_SECOND + micros)
}
