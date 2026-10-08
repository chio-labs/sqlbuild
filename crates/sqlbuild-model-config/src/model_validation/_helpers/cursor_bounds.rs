//! `cursor_start` and `cursor_end` values Python certainly accepts, with their ordering keys.

use crate::model_validation::constants::{
    CLOCK_FIELD_LENGTH, CLOCK_PART_COUNTS, CLOCK_PARTS_WITH_SECONDS, INTEGER_CURSOR,
    ISO_DATE_LENGTH, ISO_DATE_SEPARATOR_OFFSETS, LAST_SHIFTED_MONTH, MAX_HOUR, MAX_MINUTE,
    TIMESTAMP_CURSOR, UTC_OFFSET_LENGTH,
};
use crate::model_validation::models::Rejected;
use crate::types::AuthoredNode;

const MICROS_PER_SECOND: i128 = 1_000_000;
const SECONDS_PER_DAY: i128 = 86_400;
const SECONDS_PER_HOUR: i128 = 3_600;
const SECONDS_PER_MINUTE: i128 = 60;
const CIVIL_EPOCH_OFFSET_DAYS: i128 = 719_468;
const FRACTION_DIGITS: [usize; 2] = [3, 6];

/// Return the `_cursor_contract_key` order key: UTC microseconds, or the integer itself.
pub(crate) fn cursor_bound_key<N: AuthoredNode>(
    value: &N,
    cursor_type: &str,
) -> Result<i128, Rejected> {
    if let Some(number) = value.integer().filter(|_| cursor_type == INTEGER_CURSOR) {
        return Ok(i128::from(number));
    }
    let text = value.text().ok_or(Rejected)?;
    match cursor_type {
        INTEGER_CURSOR => integer_key(&text),
        TIMESTAMP_CURSOR => timestamp_key(&text),
        _ => Err(Rejected),
    }
}

/// Return whether two timestamp keys keep their order through Python's float timestamps.
pub(crate) fn keys_ordered(start: i128, end: i128, cursor_type: &str) -> bool {
    if cursor_type == TIMESTAMP_CURSOR {
        end - start >= MICROS_PER_SECOND
    } else {
        start < end
    }
}

fn integer_key(text: &str) -> Result<i128, Rejected> {
    let digits = text.strip_prefix(['+', '-']).unwrap_or(text);
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(Rejected);
    }
    text.strip_prefix('+')
        .unwrap_or(text)
        .parse()
        .map_err(|_| Rejected)
}

fn timestamp_key(text: &str) -> Result<i128, Rejected> {
    if !text.is_ascii() {
        return Err(Rejected);
    }
    let clock_start = ISO_DATE_LENGTH + 1;
    let (date, time) = match text.len() {
        ISO_DATE_LENGTH => (text, None),
        length
            if length > clock_start && matches!(text.as_bytes()[ISO_DATE_LENGTH], b'T' | b' ') =>
        {
            (&text[..ISO_DATE_LENGTH], Some(&text[clock_start..]))
        }
        _ => return Err(Rejected),
    };
    let days = date_days(date)?;
    let (micros, offset_seconds) = match time {
        None => (0, 0),
        Some(clock) => clock_micros(clock)?,
    };
    Ok((days * SECONDS_PER_DAY - offset_seconds) * MICROS_PER_SECOND + micros)
}

fn date_days(date: &str) -> Result<i128, Rejected> {
    let bytes = date.as_bytes();
    let [year_end, month_end] = ISO_DATE_SEPARATOR_OFFSETS;
    if bytes[year_end] != b'-' || bytes[month_end] != b'-' {
        return Err(Rejected);
    }
    let year = number(&date[..year_end])?;
    let month = number(&date[year_end + 1..month_end])?;
    let day = number(&date[month_end + 1..])?;
    if year == 0 || !(1..=12).contains(&month) || day == 0 || day > month_days(year, month) {
        return Err(Rejected);
    }
    Ok(days_from_civil(year, month, day))
}

fn clock_micros(clock: &str) -> Result<(i128, i128), Rejected> {
    let (clock, offset_seconds) = split_offset(clock)?;
    let (hms, fraction) = clock
        .split_once('.')
        .map_or((clock, None), |(hms, fraction)| (hms, Some(fraction)));
    let parts: Vec<&str> = hms.split(':').collect();
    if !CLOCK_PART_COUNTS.contains(&parts.len())
        || parts.iter().any(|part| part.len() != CLOCK_FIELD_LENGTH)
        || (fraction.is_some() && parts.len() != CLOCK_PARTS_WITH_SECONDS)
    {
        return Err(Rejected);
    }
    let hour = number(parts[0])?;
    let minute = number(parts[1])?;
    let second = parts.get(2).map_or(Ok(0), |part| number(part))?;
    if hour > MAX_HOUR || minute > MAX_MINUTE || second > MAX_MINUTE {
        return Err(Rejected);
    }
    let fraction_micros = match fraction {
        None => 0,
        Some(digits) if FRACTION_DIGITS.contains(&digits.len()) => {
            number(digits)? * 10_i128.pow(6 - u32::try_from(digits.len()).map_err(|_| Rejected)?)
        }
        Some(_) => return Err(Rejected),
    };
    let seconds = hour * SECONDS_PER_HOUR + minute * SECONDS_PER_MINUTE + second;
    Ok((
        seconds * MICROS_PER_SECOND + fraction_micros,
        offset_seconds,
    ))
}

fn split_offset(clock: &str) -> Result<(&str, i128), Rejected> {
    if let Some(clock) = clock.strip_suffix('Z') {
        return Ok((clock, 0));
    }
    let Some(sign_index) = clock.rfind(['+', '-']) else {
        return Ok((clock, 0));
    };
    let offset = &clock[sign_index + 1..];
    let bytes = offset.as_bytes();
    if offset.len() != UTC_OFFSET_LENGTH || bytes[CLOCK_FIELD_LENGTH] != b':' {
        return Err(Rejected);
    }
    let hours = number(&offset[..CLOCK_FIELD_LENGTH])?;
    let minutes = number(&offset[CLOCK_FIELD_LENGTH + 1..])?;
    if hours > MAX_HOUR || minutes > MAX_MINUTE {
        return Err(Rejected);
    }
    let magnitude = hours * SECONDS_PER_HOUR + minutes * SECONDS_PER_MINUTE;
    let sign = if clock.as_bytes()[sign_index] == b'-' {
        -1
    } else {
        1
    };
    Ok((&clock[..sign_index], sign * magnitude))
}

fn number(digits: &str) -> Result<i128, Rejected> {
    if digits.is_empty() || !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(Rejected);
    }
    digits.parse().map_err(|_| Rejected)
}

fn month_days(year: i128, month: i128) -> i128 {
    match month {
        2 if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

fn days_from_civil(year: i128, month: i128, day: i128) -> i128 {
    let shifted_year = if month <= LAST_SHIFTED_MONTH {
        year - 1
    } else {
        year
    };
    let era = shifted_year.div_euclid(400);
    let year_of_era = shifted_year - era * 400;
    let shifted_month = (month + 9) % 12;
    let day_of_year = (153 * shifted_month + 2) / 5 + day - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    era * 146_097 + day_of_era - CIVIL_EPOCH_OFFSET_DAYS
}
