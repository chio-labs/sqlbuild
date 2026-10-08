//! `cursor_start` and `cursor_end` checks with the errors Python raises, and their ordering keys.

use crate::model_validation::_helpers::config::{ConfigView, python_text_repr, text_if_string};
use crate::model_validation::_helpers::text::python_strip;
use crate::model_validation::constants::{
    CLOCK_FIELD_LENGTH, CLOCK_PART_COUNTS, CLOCK_PARTS_WITH_SECONDS, DECIMAL_SPECIAL_PREFIXES,
    INTEGER_CURSOR, ISO_DATE_LENGTH, ISO_DATE_SEPARATOR_OFFSETS, LAST_SHIFTED_MONTH, MAX_HOUR,
    MAX_MINUTE, MAX_YEAR, MIN_YEAR, TIMESTAMP_CURSOR, UTC_OFFSET_LENGTH,
};
use crate::model_validation::models::{Rejected, ValidationStop};
use crate::model_validation::types::Check;
use crate::types::{AuthoredNode, NodeKind};

const MICROS_PER_SECOND: i128 = 1_000_000;
const SECONDS_PER_DAY: i128 = 86_400;
const SECONDS_PER_HOUR: i128 = 3_600;
const SECONDS_PER_MINUTE: i128 = 60;
const CIVIL_EPOCH_OFFSET_DAYS: i128 = 719_468;
const DAYS_PER_ERA: i128 = 146_097;
const FRACTION_DIGITS: [usize; 2] = [3, 6];
const MICROSECOND_DIGITS: u32 = 6;
/// January's month index when months count from March.
const MARCH_BASED_JANUARY: i128 = 10;
const DECIMAL_SYNTAX: &str = "0123456789+-.eE";

/// A bound's `_cursor_contract_key`, or the overflow Python reports while shifting it to UTC.
pub(crate) enum BoundKey {
    /// UTC microseconds, or the integer itself.
    Key(i128),
    /// The UTC shift leaves years 1-9999; the text is the value's ISO form at UTC.
    Overflow(String),
}

/// A parsed ISO timestamp.
struct Timestamp {
    days: i128,
    clock_micros: i128,
    /// The UTC offset in seconds, or `None` for a naive value.
    offset_seconds: Option<i128>,
}

/// Check one bound as `_validate_timestamp_cursor_start` or `_validate_integer_cursor_start` does.
pub(crate) fn check_bound<N: AuthoredNode>(
    config: &ConfigView<'_, N>,
    bound: &N,
    cursor_type: Option<&str>,
) -> Check {
    match cursor_type {
        Some(TIMESTAMP_CURSOR) => check_timestamp_bound(config, bound),
        Some(INTEGER_CURSOR) => check_integer_bound(config, bound),
        _ => Ok(()),
    }
}

fn check_timestamp_bound<N: AuthoredNode>(config: &ConfigView<'_, N>, bound: &N) -> Check {
    match bound.kind() {
        NodeKind::Str => {
            let text = bound.text().ok_or(Rejected)?;
            parse_timestamp(&text)
                .map(|_| ())
                .or_else(|Rejected| invalid_timestamp(config, &text))
        }
        NodeKind::Other => Err(ValidationStop::Defer),
        _ => Err(config
            .error("cursor_start for cursor_type=timestamp must be a string or date-like value")),
    }
}

/// Raise Python's error for an ASCII string without digits, which no ISO form parses; else defer.
fn invalid_timestamp<N: AuthoredNode>(config: &ConfigView<'_, N>, text: &str) -> Check {
    if !text.is_ascii() || text.bytes().any(|byte| byte.is_ascii_digit()) {
        return Err(ValidationStop::Defer);
    }
    let repr = python_text_repr(text)?;
    Err(config.error(format!(
        "cursor_start value '{text}' is not a valid ISO timestamp: Invalid isoformat string: \
         {repr}"
    )))
}

fn check_integer_bound<N: AuthoredNode>(config: &ConfigView<'_, N>, bound: &N) -> Check {
    match bound.kind() {
        NodeKind::Bool(_) => {
            Err(config.error("cursor_start for cursor_type=integer must be an integer"))
        }
        NodeKind::Int { .. } => Ok(()),
        NodeKind::Str => {
            let text = bound.text().ok_or(Rejected)?;
            match plain_decimal(&text) {
                Some((_, fraction)) if fraction.bytes().all(|byte| byte == b'0') => Ok(()),
                Some(_) => {
                    Err(config.error(format!("cursor_start value '{text}' is not a whole number")))
                }
                None if certainly_not_decimal(&text)? => Err(config.error(format!(
                    "cursor_start value '{text}' is not a valid integer"
                ))),
                None => Err(ValidationStop::Defer),
            }
        }
        _ => Err(config.error("cursor_start for cursor_type=integer must be a string or integer")),
    }
}

/// Split `[+-]digits[.digits]` into its signed whole part and fraction digits.
fn plain_decimal(text: &str) -> Option<(&str, &str)> {
    let unsigned = text.strip_prefix(['+', '-']).unwrap_or(text);
    let (whole, fraction) = unsigned.split_once('.').unwrap_or((unsigned, ""));
    let digits = |part: &str| part.bytes().all(|byte| byte.is_ascii_digit());
    let has_fraction = unsigned.contains('.');
    if whole.is_empty()
        || !digits(whole)
        || !digits(fraction)
        || (has_fraction && fraction.is_empty())
    {
        return None;
    }
    Some((&text[..text.len() - unsigned.len() + whole.len()], fraction))
}

/// Return whether `Decimal(text)` certainly raises `InvalidOperation`, or reject non-ASCII text.
fn certainly_not_decimal(text: &str) -> Result<bool, Rejected> {
    let stripped: String = python_strip(text)?.replace('_', "");
    if stripped.is_empty() {
        return Ok(true);
    }
    let special = stripped.trim_start_matches(['+', '-']).to_ascii_lowercase();
    Ok(stripped
        .chars()
        .any(|character| !DECIMAL_SYNTAX.contains(character))
        && !DECIMAL_SPECIAL_PREFIXES
            .iter()
            .any(|prefix| special.starts_with(prefix)))
}

/// Return the `_cursor_contract_key` of a bound that passed its checks, or reject.
pub(crate) fn bound_key<N: AuthoredNode>(
    value: &N,
    cursor_type: &str,
) -> Result<BoundKey, Rejected> {
    if let Some(number) = value.integer().filter(|_| cursor_type == INTEGER_CURSOR) {
        return Ok(BoundKey::Key(i128::from(number)));
    }
    let text = text_if_string(value)?.ok_or(Rejected)?;
    match cursor_type {
        INTEGER_CURSOR => integer_key(&text).map(BoundKey::Key),
        TIMESTAMP_CURSOR => timestamp_key(&text),
        _ => Err(Rejected),
    }
}

/// Return whether `start < end` as Python compares the keys, or reject when floats may tie.
pub(crate) fn keys_ordered(start: i128, end: i128, cursor_type: &str) -> Result<bool, Rejected> {
    if cursor_type != TIMESTAMP_CURSOR || start >= end {
        return Ok(start < end);
    }
    if end - start >= MICROS_PER_SECOND {
        Ok(true)
    } else {
        Err(Rejected)
    }
}

fn integer_key(text: &str) -> Result<i128, Rejected> {
    let (whole, fraction) = plain_decimal(text).ok_or(Rejected)?;
    if !fraction.bytes().all(|byte| byte == b'0') {
        return Err(Rejected);
    }
    whole
        .strip_prefix('+')
        .unwrap_or(whole)
        .parse()
        .map_err(|_| Rejected)
}

fn timestamp_key(text: &str) -> Result<BoundKey, Rejected> {
    let timestamp = parse_timestamp(text)?;
    let local_micros =
        timestamp.days * SECONDS_PER_DAY * MICROS_PER_SECOND + timestamp.clock_micros;
    let utc_micros = local_micros - timestamp.offset_seconds.unwrap_or(0) * MICROS_PER_SECOND;
    let day_micros = SECONDS_PER_DAY * MICROS_PER_SECOND;
    let first_micros = days_from_civil(MIN_YEAR, 1, 1) * day_micros;
    let end_micros = days_from_civil(MAX_YEAR + 1, 1, 1) * day_micros;
    if utc_micros < first_micros || utc_micros >= end_micros {
        return Ok(BoundKey::Overflow(utc_isoformat(&timestamp)));
    }
    Ok(BoundKey::Key(utc_micros))
}

/// Return `parsed.replace(tzinfo=UTC).isoformat()`.
fn utc_isoformat(timestamp: &Timestamp) -> String {
    let (year, month, day) = civil_from_days(timestamp.days);
    let seconds = timestamp.clock_micros / MICROS_PER_SECOND;
    let micros = timestamp.clock_micros % MICROS_PER_SECOND;
    let clock = format!(
        "{:02}:{:02}:{:02}",
        seconds / SECONDS_PER_HOUR,
        seconds % SECONDS_PER_HOUR / SECONDS_PER_MINUTE,
        seconds % SECONDS_PER_MINUTE
    );
    let fraction = if micros == 0 {
        String::new()
    } else {
        format!(".{micros:06}")
    };
    format!("{year:04}-{month:02}-{day:02}T{clock}{fraction}+00:00")
}

fn parse_timestamp(text: &str) -> Result<Timestamp, Rejected> {
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
    let (clock_micros, offset_seconds) = match time {
        None => (0, None),
        Some(clock) => clock_micros(clock)?,
    };
    Ok(Timestamp {
        days,
        clock_micros,
        offset_seconds,
    })
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

fn clock_micros(clock: &str) -> Result<(i128, Option<i128>), Rejected> {
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
            let scale = MICROSECOND_DIGITS - u32::try_from(digits.len()).map_err(|_| Rejected)?;
            number(digits)? * 10_i128.pow(scale)
        }
        Some(_) => return Err(Rejected),
    };
    let seconds = hour * SECONDS_PER_HOUR + minute * SECONDS_PER_MINUTE + second;
    Ok((
        seconds * MICROS_PER_SECOND + fraction_micros,
        offset_seconds,
    ))
}

fn split_offset(clock: &str) -> Result<(&str, Option<i128>), Rejected> {
    if let Some(clock) = clock.strip_suffix('Z') {
        return Ok((clock, Some(0)));
    }
    let Some(sign_index) = clock.rfind(['+', '-']) else {
        return Ok((clock, None));
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
    Ok((&clock[..sign_index], Some(sign * magnitude)))
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
    era * DAYS_PER_ERA + day_of_era - CIVIL_EPOCH_OFFSET_DAYS
}

fn civil_from_days(days: i128) -> (i128, i128, i128) {
    let shifted = days + CIVIL_EPOCH_OFFSET_DAYS;
    let era = shifted.div_euclid(DAYS_PER_ERA);
    let day_of_era = shifted - era * DAYS_PER_ERA;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let shifted_month = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * shifted_month + 2) / 5 + 1;
    let month = if shifted_month < MARCH_BASED_JANUARY {
        shifted_month + 3
    } else {
        shifted_month - 9
    };
    let year = year_of_era + era * 400 + i128::from(month <= LAST_SHIFTED_MONTH);
    (year, month, day)
}
