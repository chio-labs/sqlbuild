//! The UTC instant of an ISO 8601 timestamp `datetime.isoformat()` wrote.

use crate::cost_report::constants::{
    DAYS_PER_ERA, LAST_SHIFTED_MONTH, MAX_HOUR, MAX_MINUTE, MAX_MONTH, MICROS_PER_SECOND,
    MICROSECOND_DIGITS, SECONDS_PER_DAY, SECONDS_PER_HOUR, SECONDS_PER_MINUTE, SHIFTED_JANUARY,
    UNIX_EPOCH_DAYS_FROM_ERA_START, YEARS_PER_ERA,
};

/// A parsed timestamp: its wall-clock fields and its UTC offset, when it has one.
pub(crate) struct Timestamp {
    /// Microseconds since the Unix epoch of the wall-clock time read as UTC.
    pub(crate) local_micros: i128,
    pub(crate) offset_seconds: Option<i128>,
}

fn number(text: &[u8], count: usize) -> Option<(u32, &[u8])> {
    if text.len() < count || !text[..count].iter().all(u8::is_ascii_digit) {
        return None;
    }
    let value: u32 = text[..count]
        .iter()
        .fold(0, |total, digit| total * 10 + u32::from(digit - b'0'));
    Some((value, &text[count..]))
}

fn leap(year: i64) -> bool {
    (year % 4 == 0 && year % 100 != 0) || year % YEARS_PER_ERA == 0
}

fn month_days(year: i64, month: u32) -> u32 {
    match month {
        2 if leap(year) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

/// Days since 1970-01-01 of a proleptic Gregorian date.
fn epoch_days(year: i64, month: u32, day: u32) -> i64 {
    let shifted_year: i64 = if month <= LAST_SHIFTED_MONTH {
        year - 1
    } else {
        year
    };
    let era: i64 = shifted_year.div_euclid(YEARS_PER_ERA);
    let year_of_era: i64 = shifted_year - era * YEARS_PER_ERA;
    let shifted_month: i64 = (i64::from(month) + 9) % 12;
    let day_of_year: i64 = (153 * shifted_month + 2) / 5 + i64::from(day) - 1;
    let day_of_era: i64 = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * DAYS_PER_ERA + day_of_era - UNIX_EPOCH_DAYS_FROM_ERA_START
}

/// The civil date of days since 1970-01-01.
fn civil(days: i64) -> (i64, u32, u32) {
    let shifted: i64 = days + UNIX_EPOCH_DAYS_FROM_ERA_START;
    let era: i64 = shifted.div_euclid(DAYS_PER_ERA);
    let day_of_era: i64 = shifted - era * DAYS_PER_ERA;
    let year_of_era: i64 =
        (day_of_era - day_of_era / 1460 + day_of_era / 36524 - day_of_era / 146_096) / 365;
    let day_of_year: i64 = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let shifted_month: i64 = (5 * day_of_year + 2) / 153;
    let day: u32 = u32::try_from(day_of_year - (153 * shifted_month + 2) / 5 + 1).unwrap_or(1);
    let month: u32 = u32::try_from(if shifted_month < SHIFTED_JANUARY {
        shifted_month + 3
    } else {
        shifted_month - 9
    })
    .unwrap_or(1);
    let year: i64 = year_of_era + era * YEARS_PER_ERA + i64::from(month <= LAST_SHIFTED_MONTH);
    (year, month, day)
}

/// `HH[:MM[:SS[.fff|.ffffff]]]` as seconds and microseconds, with the rest of the text.
fn clock(text: &[u8]) -> Option<(i128, i128, &[u8])> {
    let (hour, mut rest) = number(text, 2)?;
    let mut seconds: i128 = i128::from(hour) * SECONDS_PER_HOUR;
    if hour > MAX_HOUR {
        return None;
    }
    for scale in [SECONDS_PER_MINUTE, 1] {
        let Some(after) = rest.strip_prefix(b":") else {
            break;
        };
        let (value, after) = number(after, 2)?;
        if value > MAX_MINUTE {
            return None;
        }
        seconds += i128::from(value) * scale;
        rest = after;
    }
    let mut micros: i128 = 0;
    if let Some(after) = rest.strip_prefix(b".") {
        let length: usize = after
            .iter()
            .take_while(|byte| byte.is_ascii_digit())
            .count();
        if length == 0 || length > MICROSECOND_DIGITS {
            return None;
        }
        let (value, after) = number(after, length)?;
        let Ok(missing) = u32::try_from(MICROSECOND_DIGITS - length) else {
            return None;
        };
        micros = i128::from(value) * 10_i128.pow(missing);
        rest = after;
    }
    Some((seconds, micros, rest))
}

fn offset(text: &[u8]) -> Option<Option<i128>> {
    if text.is_empty() {
        return Some(None);
    }
    if text == b"Z" {
        return Some(Some(0));
    }
    let (sign, rest): (i128, &[u8]) = match text.first()? {
        b'+' => (1, &text[1..]),
        b'-' => (-1, &text[1..]),
        _ => return None,
    };
    let (seconds, micros, rest) = clock(rest)?;
    if !rest.is_empty() || micros != 0 {
        return None;
    }
    Some(Some(sign * seconds))
}

/// `datetime.fromisoformat` for the forms `isoformat()` writes.
pub(crate) fn parse(text: &str) -> Option<Timestamp> {
    let bytes: &[u8] = text.as_bytes();
    let (year, rest) = number(bytes, 4)?;
    let (month, rest) = number(rest.strip_prefix(b"-")?, 2)?;
    let (day, rest) = number(rest.strip_prefix(b"-")?, 2)?;
    let year: i64 = i64::from(year);
    if !(1..=MAX_MONTH).contains(&month) || day == 0 || day > month_days(year, month) {
        return None;
    }
    let days: i128 = i128::from(epoch_days(year, month, day));
    let (seconds, micros, rest) = match rest.first() {
        None => (0, 0, rest),
        Some(b'T' | b' ') => clock(&rest[1..])?,
        Some(_) => return None,
    };
    Some(Timestamp {
        local_micros: (days * SECONDS_PER_DAY + seconds) * MICROS_PER_SECOND + micros,
        offset_seconds: offset(rest)?,
    })
}

/// Microseconds since the Unix epoch, for an aware timestamp.
pub(crate) fn utc_micros(text: &str) -> Option<i128> {
    let timestamp: Timestamp = parse(text)?;
    Some(timestamp.local_micros - timestamp.offset_seconds? * MICROS_PER_SECOND)
}

/// `astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")` of an aware timestamp.
pub(crate) fn utc_text(text: &str) -> Option<String> {
    let seconds: i128 = utc_micros(text)?.div_euclid(MICROS_PER_SECOND);
    let Ok(days) = i64::try_from(seconds.div_euclid(SECONDS_PER_DAY)) else {
        return None;
    };
    let clock: i128 = seconds.rem_euclid(SECONDS_PER_DAY);
    let (year, month, day) = civil(days);
    Some(format!(
        "{year:04}-{month:02}-{day:02} {:02}:{:02}:{:02}",
        clock / SECONDS_PER_HOUR,
        clock % SECONDS_PER_HOUR / SECONDS_PER_MINUTE,
        clock % SECONDS_PER_MINUTE
    ))
}
