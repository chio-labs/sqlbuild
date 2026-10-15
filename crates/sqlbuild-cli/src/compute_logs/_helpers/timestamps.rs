//! UTC timestamps as Python's `datetime.isoformat()` writes them, with `Z` for `+00:00`.

use std::time::{SystemTime, UNIX_EPOCH};

use crate::compute_logs::constants::{
    CAPTURE_DATE_LENGTH, DAYS_PER_ERA, EPOCH_DAY_OFFSET, FEBRUARY, HOURS_PER_DAY,
    MARCH_BASED_JANUARY, MAX_DAY_OF_MONTH, MICROSECOND_DIGITS, MICROSECONDS_PER_SECOND,
    MONTHS_PER_YEAR, SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE, YEARS_PER_ERA,
};

/// Microseconds since the Unix epoch of `instant`.
pub(crate) fn epoch_microseconds(instant: SystemTime) -> i64 {
    match instant.duration_since(UNIX_EPOCH) {
        Ok(elapsed) => i64::try_from(elapsed.as_micros()).unwrap_or(i64::MAX),
        Err(_) => 0,
    }
}

/// The proleptic Gregorian `(year, month, day)` of days since 1970-01-01 (Hinnant's algorithm).
fn civil_date(days: i64) -> (i64, i64, i64) {
    let shifted = days + EPOCH_DAY_OFFSET;
    let era = shifted.div_euclid(DAYS_PER_ERA);
    let day_of_era = shifted.rem_euclid(DAYS_PER_ERA);
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_index = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_index + 2) / 5 + 1;
    let month = month_index
        + if month_index < MARCH_BASED_JANUARY {
            3
        } else {
            -9
        };
    let year = year_of_era + era * YEARS_PER_ERA + i64::from(month <= FEBRUARY);
    (year, month, day)
}

/// Days since 1970-01-01 of a proleptic Gregorian date (Hinnant's algorithm).
fn days_from_civil(year: i64, month: i64, day: i64) -> i64 {
    let shifted_year = year - i64::from(month <= FEBRUARY);
    let era = shifted_year.div_euclid(YEARS_PER_ERA);
    let year_of_era = shifted_year.rem_euclid(YEARS_PER_ERA);
    let month_index = month + if month > FEBRUARY { -3 } else { 9 };
    let day_of_year = (153 * month_index + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * DAYS_PER_ERA + day_of_era - EPOCH_DAY_OFFSET
}

/// `YYYY-MM-DD` of a UTC instant, as `capture_date`.
pub(crate) fn utc_date(microseconds: i64) -> String {
    let (year, month, day) =
        civil_date(microseconds.div_euclid(MICROSECONDS_PER_SECOND * SECONDS_PER_DAY));
    format!("{year:04}-{month:02}-{day:02}")
}

/// `datetime.isoformat()` of a UTC instant with `+00:00` written as `Z`.
pub(crate) fn utc_timestamp(microseconds: i64) -> String {
    let of_day = microseconds
        .div_euclid(MICROSECONDS_PER_SECOND)
        .rem_euclid(SECONDS_PER_DAY);
    let fraction = microseconds.rem_euclid(MICROSECONDS_PER_SECOND);
    let fraction_text = match fraction {
        0 => String::new(),
        _ => format!(".{fraction:06}"),
    };
    format!(
        "{}T{:02}:{:02}:{:02}{fraction_text}Z",
        utc_date(microseconds),
        of_day / SECONDS_PER_HOUR,
        of_day % SECONDS_PER_HOUR / SECONDS_PER_MINUTE,
        of_day % SECONDS_PER_MINUTE
    )
}

fn number(text: &str) -> Option<i64> {
    let Ok(value) = text.parse::<i64>() else {
        return None;
    };
    Some(value)
}

fn offset_seconds(text: &str) -> Option<i64> {
    let (sign, body) = match text.as_bytes().first()? {
        b'+' => (1, text.get(1..)?),
        b'-' => (-1, text.get(1..)?),
        _ => return None,
    };
    let (whole, _fraction) = body.split_once('.').unwrap_or((body, ""));
    let parts: Vec<i64> = whole.split(':').map(number).collect::<Option<_>>()?;
    let seconds = match parts.as_slice() {
        [hours, minutes] => hours * SECONDS_PER_HOUR + minutes * SECONDS_PER_MINUTE,
        [hours, minutes, seconds] => {
            hours * SECONDS_PER_HOUR + minutes * SECONDS_PER_MINUTE + seconds
        }
        _ => return None,
    };
    Some(sign * seconds)
}

/// UTC microseconds and awareness of `datetime.fromisoformat(text)`, or `None` when unparsable.
pub(crate) fn parse_iso_instant(text: &str) -> Option<(i64, bool)> {
    let date = text.get(..CAPTURE_DATE_LENGTH)?;
    let rest = text.get(CAPTURE_DATE_LENGTH + 1..)?;
    let split = rest.find(['+', '-']).unwrap_or(rest.len());
    let (clock, offset) = rest.split_at(split);
    let (whole, fraction) = clock.split_once('.').unwrap_or((clock, ""));
    let dates: Vec<i64> = date.split('-').map(number).collect::<Option<_>>()?;
    let clocks: Vec<i64> = whole.split(':').map(number).collect::<Option<_>>()?;
    let ([year, month, day], [hour, minute, second]) = (dates.as_slice(), clocks.as_slice()) else {
        return None;
    };
    let in_range = (1..=MONTHS_PER_YEAR).contains(month)
        && (1..=MAX_DAY_OF_MONTH).contains(day)
        && (0..HOURS_PER_DAY).contains(hour)
        && (0..SECONDS_PER_MINUTE).contains(minute)
        && (0..SECONDS_PER_MINUTE).contains(second);
    if !in_range || !fraction.bytes().all(|byte| byte.is_ascii_digit()) {
        return None;
    }
    let micros = match fraction {
        "" => 0,
        digits => number(format!("{digits:0<6}").get(..MICROSECOND_DIGITS)?)?,
    };
    let local = (days_from_civil(*year, *month, *day) * SECONDS_PER_DAY
        + hour * SECONDS_PER_HOUR
        + minute * SECONDS_PER_MINUTE
        + second)
        * MICROSECONDS_PER_SECOND
        + micros;
    if offset.is_empty() {
        return Some((local, false));
    }
    Some((
        local - offset_seconds(offset)? * MICROSECONDS_PER_SECOND,
        true,
    ))
}
