//! CPython's `datetime.fromisoformat`; reads past the end of the text see the C parser's NUL.

/// One parsed date and time, before CPython's range checks.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct IsoDateTime {
    pub(crate) year: i64,
    pub(crate) month: i64,
    pub(crate) day: i64,
    pub(crate) hour: i64,
    pub(crate) minute: i64,
    pub(crate) second: i64,
    pub(crate) microsecond: i64,
    /// The UTC offset in microseconds, or `None` for a naive value.
    pub(crate) offset_micros: Option<i64>,
}

use crate::model_validation::constants::{
    BASIC_WEEK_DATE_LENGTH, CENTURY, CLOCK_COMPONENTS, DAYS_BEFORE_MONTH, DAYS_IN_MONTH,
    DAYS_PER_4_YEARS, DAYS_PER_400_YEARS, DAYS_PER_CENTURY, DAYS_PER_WEEK, DAYS_PER_YEAR,
    DECEMBER_INDEX, EXTENDED_DATE_LENGTH, EXTENDED_WEEK_DATE_LENGTH, EXTENDED_WEEK_DAY_LENGTH,
    FEBRUARY, FRACTION_CORRECTION, FRACTION_DIGITS, GREGORIAN_CYCLE, HOURS_PER_DAY, LAST_HOUR,
    LAST_MINUTE, LAST_SECOND, LEAP_CYCLE, LONG_YEAR_WEEKS, MAX_YEAR, MICROS_PER_DAY,
    MICROS_PER_SECOND, MIN_YEAR, MONTHS_PER_YEAR, ORDINAL_MONTH_BIAS, ORDINAL_MONTH_SHIFT,
    PYTHON_313, PYTHON_314, SECONDS_PER_HOUR, SECONDS_PER_MINUTE, THURSDAY, WEDNESDAY,
    WEEK_DATE_MARK_INDEX, YEAR_DIGITS,
};
use crate::model_validation::errors::IsoError;

/// A clock read by `parse_hh_mm_ss_ff`: hour, minute, second, microsecond.
type Clock = [i64; 4];

/// The byte span `[start, end)` a clock or time is read from.
#[derive(Clone, Copy)]
struct Span {
    start: usize,
    end: usize,
}

/// Parse `text` as `datetime.fromisoformat` does on CPython 3.`minor`.
pub(crate) fn datetime_fromisoformat(text: &str, minor: u8) -> Result<IsoDateTime, IsoError> {
    let bytes: &[u8] = text.as_bytes();
    let length: usize = bytes.len();
    let separator: Option<usize> = isoformat_separator(bytes);
    let (year, month, day) =
        parse_date(bytes, separator.unwrap_or(usize::MAX)).map_err(|_| IsoError::InvalidString)?;
    let (time, has_offset): (TimeFields, bool) =
        match separator.filter(|separator| length > *separator) {
            Some(separator) => {
                let start: usize = separator + utf8_width(byte_at(bytes, separator));
                parse_time(bytes, Span { start, end: length }, minor)
                    .map_err(|_| IsoError::InvalidString)?
            }
            None => (TimeFields::default(), false),
        };
    let offset_micros: Option<i64> = has_offset
        .then(|| time.offset_seconds * MICROS_PER_SECOND + time.offset_micros)
        .map(|offset| checked_offset(offset, time.offset_seconds, minor))
        .transpose()?;
    let parsed = IsoDateTime {
        year,
        month,
        day,
        hour: time.hour,
        minute: time.minute,
        second: time.second,
        microsecond: time.microsecond,
        offset_micros,
    };
    let parsed: IsoDateTime = if minor >= PYTHON_314
        && parsed.hour == HOURS_PER_DAY
        && (1..=MONTHS_PER_YEAR).contains(&parsed.month)
    {
        roll_iso_midnight(parsed)?
    } else {
        parsed
    };
    check_ranges(&parsed)?;
    Ok(parsed)
}

/// Microseconds since 0001-01-01 00:00 of the local wall time, ignoring any offset.
pub(crate) fn local_micros(parsed: &IsoDateTime) -> i64 {
    let days: i64 = ymd_to_ordinal(parsed.year, parsed.month, parsed.day) - 1;
    let seconds: i64 =
        parsed.hour * SECONDS_PER_HOUR + parsed.minute * SECONDS_PER_MINUTE + parsed.second;
    days * MICROS_PER_DAY + seconds * MICROS_PER_SECOND + parsed.microsecond
}

/// The microseconds since 0001-01-01 of the earliest and the first excluded instant.
pub(crate) fn supported_micros() -> (i64, i64) {
    (
        0,
        ymd_to_ordinal(MAX_YEAR + 1, 1, 1).saturating_sub(1) * MICROS_PER_DAY,
    )
}

/// Microseconds from 0001-01-01 to the Unix epoch.
pub(crate) fn epoch_micros() -> i64 {
    (ymd_to_ordinal(1970, 1, 1) - 1) * MICROS_PER_DAY
}

/// `parsed.replace(tzinfo=UTC).isoformat()`.
pub(crate) fn utc_isoformat(parsed: &IsoDateTime) -> String {
    let fraction: String = if parsed.microsecond == 0 {
        String::new()
    } else {
        format!(".{:06}", parsed.microsecond)
    };
    format!(
        "{:04}-{:02}-{:02}T{:02}:{:02}:{:02}{fraction}+00:00",
        parsed.year, parsed.month, parsed.day, parsed.hour, parsed.minute, parsed.second
    )
}

#[derive(Clone, Copy, Default)]
struct TimeFields {
    hour: i64,
    minute: i64,
    second: i64,
    microsecond: i64,
    offset_seconds: i64,
    offset_micros: i64,
}

fn byte_at(bytes: &[u8], index: usize) -> u8 {
    bytes.get(index).copied().unwrap_or(0)
}

fn is_digit(byte: u8) -> bool {
    byte.is_ascii_digit()
}

/// The UTF-8 length of the character starting with `lead`, as CPython skips the separator.
fn utf8_width(lead: u8) -> usize {
    if lead & 0x80 == 0 {
        1
    } else {
        match lead & 0xf0 {
            0xe0 => 3,
            0xf0 => 4,
            _ => 2,
        }
    }
}

/// `_find_isoformat_datetime_separator`; `None` stands for its -1.
fn isoformat_separator(bytes: &[u8]) -> Option<usize> {
    let length: usize = bytes.len();
    if length == BASIC_WEEK_DATE_LENGTH {
        return Some(BASIC_WEEK_DATE_LENGTH);
    }
    if byte_at(bytes, YEAR_DIGITS) == b'-' {
        if byte_at(bytes, WEEK_DATE_MARK_INDEX) != b'W' {
            return Some(EXTENDED_DATE_LENGTH);
        }
        if length < EXTENDED_WEEK_DATE_LENGTH {
            return None;
        }
        if length > EXTENDED_WEEK_DATE_LENGTH && byte_at(bytes, EXTENDED_WEEK_DATE_LENGTH) == b'-' {
            if length == EXTENDED_WEEK_DATE_LENGTH + 1 {
                return None;
            }
            if length > EXTENDED_WEEK_DAY_LENGTH
                && is_digit(byte_at(bytes, EXTENDED_WEEK_DAY_LENGTH))
            {
                return Some(EXTENDED_WEEK_DATE_LENGTH);
            }
            return Some(EXTENDED_WEEK_DAY_LENGTH);
        }
        return Some(EXTENDED_WEEK_DATE_LENGTH);
    }
    if byte_at(bytes, YEAR_DIGITS) != b'W' {
        return Some(EXTENDED_WEEK_DATE_LENGTH);
    }
    let digits_end: usize = (BASIC_WEEK_DATE_LENGTH..length)
        .find(|index| !is_digit(byte_at(bytes, *index)))
        .unwrap_or(length.max(BASIC_WEEK_DATE_LENGTH));
    if digits_end <= EXTENDED_WEEK_DATE_LENGTH {
        return Some(digits_end);
    }
    Some(if digits_end.is_multiple_of(2) {
        BASIC_WEEK_DATE_LENGTH
    } else {
        EXTENDED_WEEK_DATE_LENGTH
    })
}

/// `parse_digits`: the position after `count` digits at `start` and their value, or `None`.
fn parse_digits(bytes: &[u8], start: usize, count: usize) -> Option<(usize, i64)> {
    let mut value: i64 = 0;
    for index in start..start + count {
        let byte: u8 = byte_at(bytes, index);
        if !is_digit(byte) {
            return None;
        }
        value = value * 10 + i64::from(byte - b'0');
    }
    Some((start + count, value))
}

/// `parse_isoformat_date`, reading the date in the first `length` bytes.
fn parse_date(bytes: &[u8], length: usize) -> Result<(i64, i64, i64), i32> {
    let (mut position, year): (usize, i64) = parse_digits(bytes, 0, YEAR_DIGITS).ok_or(-1)?;
    let uses_separator: bool = byte_at(bytes, position) == b'-';
    if uses_separator {
        position += 1;
    }
    if byte_at(bytes, position) == b'W' {
        let week: i64;
        (position, week) = parse_digits(bytes, position + 1, 2).ok_or(-3)?;
        let mut weekday: i64 = 1;
        if position < length {
            if uses_separator {
                if byte_at(bytes, position) != b'-' {
                    return Err(-2);
                }
                position += 1;
            }
            (_, weekday) = parse_digits(bytes, position, 1).ok_or(-4)?;
        }
        return iso_to_ymd(year, week, weekday);
    }
    let month: i64;
    (position, month) = parse_digits(bytes, position, 2).ok_or(-1)?;
    if uses_separator {
        if byte_at(bytes, position) != b'-' {
            return Err(-2);
        }
        position += 1;
    }
    let (_, day): (usize, i64) = parse_digits(bytes, position, 2).ok_or(-1)?;
    Ok((year, month, day))
}

/// `parse_hh_mm_ss_ff` over `span`: the clock, and whether text follows the time.
fn parse_clock(bytes: &[u8], span: Span, minor: u8) -> Result<(Clock, bool), i32> {
    let Span { start, end } = span;
    let mut fields: Clock = [0; 4];
    let mut position: usize = start;
    let mut has_separator: bool = true;
    let mut component: usize = 0;
    while component < CLOCK_COMPONENTS {
        (position, fields[component]) = parse_digits(bytes, position, 2).ok_or(-3)?;
        let character: u8 = byte_at(bytes, position);
        position += 1;
        if component == 0 {
            has_separator = character == b':';
        }
        let decimal_mark: bool = matches!(character, b'.' | b',');
        if minor >= PYTHON_313 && decimal_mark {
            if minor >= PYTHON_314 && component + 1 < CLOCK_COMPONENTS {
                return Err(-3);
            }
            if position >= end {
                return Err(-3);
            }
            break;
        }
        if position >= end {
            return Ok((fields, character != 0));
        }
        if has_separator && character == b':' {
            if minor >= PYTHON_314 && component + 1 == CLOCK_COMPONENTS {
                return Err(-4);
            }
            component += 1;
            continue;
        }
        if decimal_mark {
            break;
        }
        if !has_separator {
            position -= 1;
        } else {
            return Err(-4);
        }
        component += 1;
    }
    let to_parse: usize = end.saturating_sub(position).min(FRACTION_DIGITS);
    (position, fields[CLOCK_COMPONENTS]) = parse_digits(bytes, position, to_parse).ok_or(-3)?;
    if let Some(correction) = to_parse
        .checked_sub(1)
        .and_then(|at| FRACTION_CORRECTION.get(at))
    {
        fields[CLOCK_COMPONENTS] *= correction;
    }
    while is_digit(byte_at(bytes, position)) {
        position += 1;
    }
    Ok((fields, byte_at(bytes, position) != 0))
}

/// `parse_isoformat_time` over `span`: the time, and whether it read a UTC offset.
fn parse_time(bytes: &[u8], span: Span, minor: u8) -> Result<(TimeFields, bool), i32> {
    let Span { start, end } = span;
    let mut time = TimeFields::default();
    let mut offset_at: usize = start;
    loop {
        if matches!(byte_at(bytes, offset_at), b'Z' | b'+' | b'-') {
            break;
        }
        offset_at += 1;
        if offset_at >= end {
            break;
        }
    }
    let (clock, trailing): (Clock, bool) = parse_clock(
        bytes,
        Span {
            start,
            end: offset_at,
        },
        minor,
    )?;
    [time.hour, time.minute, time.second, time.microsecond] = clock;
    if offset_at == end {
        return if trailing { Err(-5) } else { Ok((time, false)) };
    }
    if byte_at(bytes, offset_at) == b'Z' {
        return if byte_at(bytes, offset_at + 1) == 0 {
            Ok((time, true))
        } else {
            Err(-5)
        };
    }
    let sign: i64 = if byte_at(bytes, offset_at) == b'-' {
        -1
    } else {
        1
    };
    let (offset, offset_trailing): (Clock, bool) = parse_clock(
        bytes,
        Span {
            start: offset_at + 1,
            end,
        },
        minor,
    )?;
    time.offset_seconds =
        sign * (offset[0] * SECONDS_PER_HOUR + offset[1] * SECONDS_PER_MINUTE + offset[2]);
    time.offset_micros = sign * offset[CLOCK_COMPONENTS];
    if offset_trailing {
        Err(-5)
    } else {
        Ok((time, true))
    }
}

/// `tzinfo_from_isoformat_results`: `None` for UTC, else the checked offset.
fn checked_offset(offset: i64, offset_seconds: i64, minor: u8) -> Result<i64, IsoError> {
    let utc: bool = if minor >= PYTHON_313 {
        offset == 0
    } else {
        offset_seconds == 0
    };
    if utc {
        return Ok(0);
    }
    if offset <= -MICROS_PER_DAY || offset >= MICROS_PER_DAY {
        return Err(IsoError::Message(format!(
            "offset must be a timedelta strictly between -timedelta(hours=24) and \
             timedelta(hours=24), not {}.",
            timedelta_repr(offset)
        )));
    }
    Ok(offset)
}

/// `repr(timedelta(microseconds=micros))`.
fn timedelta_repr(micros: i64) -> String {
    let days: i64 = micros.div_euclid(MICROS_PER_DAY);
    let rest: i64 = micros.rem_euclid(MICROS_PER_DAY);
    let fields: Vec<String> = [
        ("days", days),
        ("seconds", rest / MICROS_PER_SECOND),
        ("microseconds", rest % MICROS_PER_SECOND),
    ]
    .iter()
    .filter(|(_, value)| *value != 0)
    .map(|(name, value)| format!("{name}={value}"))
    .collect();
    if fields.is_empty() {
        return "datetime.timedelta(0)".to_owned();
    }
    format!("datetime.timedelta({})", fields.join(", "))
}

/// Python 3.14's `24:00`: midnight of the next day, when the rest of the clock is zero.
fn roll_iso_midnight(mut parsed: IsoDateTime) -> Result<IsoDateTime, IsoError> {
    let month_days: i64 = days_in_month(parsed.year, parsed.month);
    if parsed.day > month_days {
        return Ok(parsed);
    }
    if parsed.minute != 0 || parsed.second != 0 || parsed.microsecond != 0 {
        return Err(IsoError::Message(
            "minute, second, and microsecond must be 0 when hour is 24".to_owned(),
        ));
    }
    parsed.hour = 0;
    parsed.day += 1;
    if parsed.day > month_days {
        parsed.day = 1;
        parsed.month += 1;
        if parsed.month > MONTHS_PER_YEAR {
            parsed.month = 1;
            parsed.year += 1;
        }
    }
    Ok(parsed)
}

/// `check_date_args` then `check_time_args`.
fn check_ranges(parsed: &IsoDateTime) -> Result<(), IsoError> {
    let message: Option<String> = if !(MIN_YEAR..=MAX_YEAR).contains(&parsed.year) {
        Some(format!("year {} is out of range", parsed.year))
    } else if !(1..=MONTHS_PER_YEAR).contains(&parsed.month) {
        Some("month must be in 1..12".to_owned())
    } else if parsed.day < 1 || parsed.day > days_in_month(parsed.year, parsed.month) {
        Some("day is out of range for month".to_owned())
    } else if !(0..=LAST_HOUR).contains(&parsed.hour) {
        Some("hour must be in 0..23".to_owned())
    } else if !(0..=LAST_MINUTE).contains(&parsed.minute) {
        Some("minute must be in 0..59".to_owned())
    } else if !(0..=LAST_SECOND).contains(&parsed.second) {
        Some("second must be in 0..59".to_owned())
    } else {
        None
    };
    message.map_or(Ok(()), |message| Err(IsoError::Message(message)))
}

/// `iso_to_ymd`, with `parse_isoformat_date`'s codes for its failures.
fn iso_to_ymd(year: i64, week: i64, weekday: i64) -> Result<(i64, i64, i64), i32> {
    if !(MIN_YEAR..=MAX_YEAR).contains(&year) {
        return Err(-7);
    }
    if week <= 0 || week >= LONG_YEAR_WEEKS {
        let first_weekday: i64 = (ymd_to_ordinal(year, 1, 1) + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
        let long_year: bool =
            first_weekday == THURSDAY || (first_weekday == WEDNESDAY && is_leap(year));
        if week != LONG_YEAR_WEEKS || !long_year {
            return Err(-5);
        }
    }
    if weekday <= 0 || weekday > DAYS_PER_WEEK {
        return Err(-6);
    }
    let first_day: i64 = ymd_to_ordinal(year, 1, 1);
    let first_weekday: i64 = (first_day + DAYS_PER_WEEK - 1) % DAYS_PER_WEEK;
    let week1_monday: i64 = first_day - first_weekday
        + if first_weekday > THURSDAY {
            DAYS_PER_WEEK
        } else {
            0
        };
    Ok(ordinal_to_ymd(
        week1_monday + (week - 1) * DAYS_PER_WEEK + weekday - 1,
    ))
}

fn is_leap(year: i64) -> bool {
    year.rem_euclid(LEAP_CYCLE) == 0
        && (year.rem_euclid(CENTURY) != 0 || year.rem_euclid(GREGORIAN_CYCLE) == 0)
}

fn days_in_month(year: i64, month: i64) -> i64 {
    let index: usize = usize::try_from(month.clamp(1, MONTHS_PER_YEAR)).unwrap_or(1);
    DAYS_IN_MONTH[index] + i64::from(month == FEBRUARY && is_leap(year))
}

fn ymd_to_ordinal(year: i64, month: i64, day: i64) -> i64 {
    let before_year: i64 = year - 1;
    let days_before_year: i64 = before_year * DAYS_PER_YEAR + before_year / LEAP_CYCLE
        - before_year / CENTURY
        + before_year / GREGORIAN_CYCLE;
    let index: usize = usize::try_from(month.clamp(1, MONTHS_PER_YEAR)).unwrap_or(1);
    days_before_year + DAYS_BEFORE_MONTH[index] + i64::from(month > FEBRUARY && is_leap(year)) + day
}

/// `ord_to_ymd`.
fn ordinal_to_ymd(ordinal: i64) -> (i64, i64, i64) {
    let mut days: i64 = ordinal - 1;
    let four_centuries: i64 = days / DAYS_PER_400_YEARS;
    days %= DAYS_PER_400_YEARS;
    let centuries: i64 = days / DAYS_PER_CENTURY;
    days %= DAYS_PER_CENTURY;
    let four_years: i64 = days / DAYS_PER_4_YEARS;
    days %= DAYS_PER_4_YEARS;
    let years: i64 = days / DAYS_PER_YEAR;
    days %= DAYS_PER_YEAR;
    let year: i64 = four_centuries * GREGORIAN_CYCLE
        + 1
        + centuries * CENTURY
        + four_years * LEAP_CYCLE
        + years;
    if years == LEAP_CYCLE || centuries == LEAP_CYCLE {
        return (year - 1, MONTHS_PER_YEAR, DAYS_IN_MONTH[DECEMBER_INDEX]);
    }
    let leap: bool = years == LEAP_CYCLE - 1
        && (four_years != CENTURY / LEAP_CYCLE - 1 || centuries == LEAP_CYCLE - 1);
    let mut month: i64 = (days + ORDINAL_MONTH_BIAS) >> ORDINAL_MONTH_SHIFT;
    let month_index: usize = usize::try_from(month).unwrap_or(1);
    let mut preceding: i64 = DAYS_BEFORE_MONTH[month_index] + i64::from(month > FEBRUARY && leap);
    if preceding > days {
        month -= 1;
        preceding -= days_in_month(year, month);
    }
    (year, month, days - preceding + 1)
}
