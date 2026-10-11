//! UTC timestamps as Python's `datetime.isoformat()` writes them, with `Z` for `+00:00`.

use std::time::{SystemTime, UNIX_EPOCH};

use crate::compute_logs::constants::{
    DAYS_PER_ERA, EPOCH_DAY_OFFSET, FEBRUARY, MARCH_BASED_JANUARY, MICROSECOND_DIGITS,
    MICROSECONDS_PER_SECOND, SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE, YEARS_PER_ERA,
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

/// Microseconds of a `YYYY-MM-DDTHH:MM:SS[.ffffff]` UTC timestamp ending in `Z` or `+00:00`.
pub(crate) fn parse_utc_timestamp(text: &str) -> Option<i64> {
    let body = text
        .strip_suffix('Z')
        .or_else(|| text.strip_suffix("+00:00"))?;
    let (date, time) = body.split_once('T')?;
    let (clock, fraction) = time.split_once('.').unwrap_or((time, ""));
    let dates: Vec<i64> = date.split('-').map(number).collect::<Option<_>>()?;
    let clocks: Vec<i64> = clock.split(':').map(number).collect::<Option<_>>()?;
    let ([year, month, day], [hour, minute, second]) = (dates.as_slice(), clocks.as_slice()) else {
        return None;
    };
    let micros = match fraction {
        "" => 0,
        digits => number(format!("{digits:0<6}").get(..MICROSECOND_DIGITS)?)?,
    };
    let seconds = days_from_civil(*year, *month, *day) * SECONDS_PER_DAY
        + hour * SECONDS_PER_HOUR
        + minute * SECONDS_PER_MINUTE
        + second;
    Some(seconds * MICROSECONDS_PER_SECOND + micros)
}
