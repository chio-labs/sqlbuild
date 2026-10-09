//! CPython's `datetime.fromisoformat`, following the C parser of each supported release.
//!
//! The C parser reads a NUL-terminated buffer; reads past the end of the text see that NUL.

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

/// Why `fromisoformat` raises `ValueError`.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum IsoError {
    /// `Invalid isoformat string: <repr>`.
    InvalidString,
    /// Any other `ValueError` message.
    Message(String),
}

const MIN_YEAR: i64 = 1;
const MAX_YEAR: i64 = 9999;
const MICROS_PER_SECOND: i64 = 1_000_000;
const MICROS_PER_DAY: i64 = 86_400 * MICROS_PER_SECOND;
const DAYS_BEFORE_MONTH: [i64; 13] = [0, 0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
const FRACTION_CORRECTION: [i64; 5] = [100_000, 10_000, 1_000, 100, 10];
const FRACTION_DIGITS: usize = 6;
const PYTHON_313: u8 = 13;
const PYTHON_314: u8 = 14;

/// Parse `text` as `datetime.fromisoformat` does on CPython 3.`minor`.
pub(crate) fn datetime_fromisoformat(text: &str, minor: u8) -> Result<IsoDateTime, IsoError> {
    let bytes: &[u8] = text.as_bytes();
    let length: usize = bytes.len();
    let separator: Option<usize> = isoformat_separator(bytes);
    let (year, month, day) =
        parse_date(bytes, separator.unwrap_or(usize::MAX)).map_err(|_| IsoError::InvalidString)?;
    let mut time = TimeFields::default();
    let mut has_offset = false;
    if let Some(separator) = separator.filter(|separator| length > *separator) {
        let start: usize = separator + utf8_width(byte_at(bytes, separator));
        has_offset = parse_time(bytes, start, length, minor, &mut time)
            .map_err(|_| IsoError::InvalidString)?;
    }
    let offset_micros: Option<i64> = has_offset
        .then(|| time.offset_seconds * MICROS_PER_SECOND + time.offset_micros)
        .map(|offset| checked_offset(offset, time.offset_seconds, minor))
        .transpose()?;
    let mut parsed = IsoDateTime {
        year,
        month,
        day,
        hour: time.hour,
        minute: time.minute,
        second: time.second,
        microsecond: time.microsecond,
        offset_micros,
    };
    if minor >= PYTHON_314 && parsed.hour == 24 && (1..=12).contains(&parsed.month) {
        roll_iso_midnight(&mut parsed)?;
    }
    check_ranges(&parsed)?;
    Ok(parsed)
}

/// Microseconds since 0001-01-01 00:00 of the local wall time, ignoring any offset.
pub(crate) fn local_micros(parsed: &IsoDateTime) -> i64 {
    let days: i64 = ymd_to_ordinal(parsed.year, parsed.month, parsed.day) - 1;
    let seconds: i64 = parsed.hour * 3_600 + parsed.minute * 60 + parsed.second;
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

#[derive(Default)]
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
    if length == 7 {
        return Some(7);
    }
    if byte_at(bytes, 4) == b'-' {
        if byte_at(bytes, 5) != b'W' {
            return Some(10);
        }
        if length < 8 {
            return None;
        }
        if length > 8 && byte_at(bytes, 8) == b'-' {
            if length == 9 {
                return None;
            }
            if length > 10 && is_digit(byte_at(bytes, 10)) {
                return Some(8);
            }
            return Some(10);
        }
        return Some(8);
    }
    if byte_at(bytes, 4) != b'W' {
        return Some(8);
    }
    let digits_end: usize = (7..length)
        .find(|index| !is_digit(byte_at(bytes, *index)))
        .unwrap_or(length.max(7));
    if digits_end < 9 {
        return Some(digits_end);
    }
    Some(if digits_end.is_multiple_of(2) { 7 } else { 8 })
}

/// `parse_digits`: read `count` digits at `start` into `value`; `None` at a non-digit.
fn parse_digits(bytes: &[u8], start: usize, count: usize, value: &mut i64) -> Option<usize> {
    for index in start..start + count {
        let byte: u8 = byte_at(bytes, index);
        if !is_digit(byte) {
            return None;
        }
        *value = *value * 10 + i64::from(byte - b'0');
    }
    Some(start + count)
}

/// `parse_isoformat_date`, reading the date in the first `length` bytes.
fn parse_date(bytes: &[u8], length: usize) -> Result<(i64, i64, i64), i32> {
    let mut year: i64 = 0;
    let mut position: usize = parse_digits(bytes, 0, 4, &mut year).ok_or(-1)?;
    let uses_separator: bool = byte_at(bytes, position) == b'-';
    if uses_separator {
        position += 1;
    }
    if byte_at(bytes, position) == b'W' {
        let mut week: i64 = 0;
        let mut weekday: i64 = 0;
        position = parse_digits(bytes, position + 1, 2, &mut week).ok_or(-3)?;
        if position < length {
            if uses_separator {
                if byte_at(bytes, position) != b'-' {
                    return Err(-2);
                }
                position += 1;
            }
            parse_digits(bytes, position, 1, &mut weekday).ok_or(-4)?;
        } else {
            weekday = 1;
        }
        return iso_to_ymd(year, week, weekday);
    }
    let mut month: i64 = 0;
    let mut day: i64 = 0;
    position = parse_digits(bytes, position, 2, &mut month).ok_or(-1)?;
    if uses_separator {
        if byte_at(bytes, position) != b'-' {
            return Err(-2);
        }
        position += 1;
    }
    parse_digits(bytes, position, 2, &mut day).ok_or(-1)?;
    Ok((year, month, day))
}

/// `parse_hh_mm_ss_ff` over `[start, end)`; `Ok(true)` when text follows the time.
fn parse_clock(
    bytes: &[u8],
    start: usize,
    end: usize,
    minor: u8,
    fields: &mut [i64; 4],
) -> Result<bool, i32> {
    *fields = [0; 4];
    let mut position: usize = start;
    let mut has_separator: bool = true;
    let mut component: usize = 0;
    while component < 3 {
        position = parse_digits(bytes, position, 2, &mut fields[component]).ok_or(-3)?;
        let character: u8 = byte_at(bytes, position);
        position += 1;
        if component == 0 {
            has_separator = character == b':';
        }
        let decimal_mark: bool = matches!(character, b'.' | b',');
        if minor >= PYTHON_313 && decimal_mark {
            if minor >= PYTHON_314 && component < 2 {
                return Err(-3);
            }
            if position >= end {
                return Err(-3);
            }
            break;
        }
        if position >= end {
            return Ok(character != 0);
        }
        if has_separator && character == b':' {
            if minor >= PYTHON_314 && component == 2 {
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
    position = parse_digits(bytes, position, to_parse, &mut fields[3]).ok_or(-3)?;
    if let Some(correction) = to_parse
        .checked_sub(1)
        .and_then(|at| FRACTION_CORRECTION.get(at))
    {
        fields[3] *= correction;
    }
    while is_digit(byte_at(bytes, position)) {
        position += 1;
    }
    Ok(byte_at(bytes, position) != 0)
}

/// `parse_isoformat_time` over `[start, end)`; `Ok(true)` when it read a UTC offset.
fn parse_time(
    bytes: &[u8],
    start: usize,
    end: usize,
    minor: u8,
    time: &mut TimeFields,
) -> Result<bool, i32> {
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
    let mut clock: [i64; 4] = [0; 4];
    let trailing: bool = parse_clock(bytes, start, offset_at, minor, &mut clock)?;
    [time.hour, time.minute, time.second, time.microsecond] = clock;
    if offset_at == end {
        return if trailing { Err(-5) } else { Ok(false) };
    }
    if byte_at(bytes, offset_at) == b'Z' {
        return if byte_at(bytes, offset_at + 1) == 0 {
            Ok(true)
        } else {
            Err(-5)
        };
    }
    let sign: i64 = if byte_at(bytes, offset_at) == b'-' {
        -1
    } else {
        1
    };
    let mut offset: [i64; 4] = [0; 4];
    let offset_trailing: bool = parse_clock(bytes, offset_at + 1, end, minor, &mut offset)?;
    time.offset_seconds = sign * (offset[0] * 3_600 + offset[1] * 60 + offset[2]);
    time.offset_micros = sign * offset[3];
    if offset_trailing { Err(-5) } else { Ok(true) }
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
fn roll_iso_midnight(parsed: &mut IsoDateTime) -> Result<(), IsoError> {
    let month_days: i64 = days_in_month(parsed.year, parsed.month);
    if parsed.day > month_days {
        return Ok(());
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
        if parsed.month > 12 {
            parsed.month = 1;
            parsed.year += 1;
        }
    }
    Ok(())
}

/// `check_date_args` then `check_time_args`.
fn check_ranges(parsed: &IsoDateTime) -> Result<(), IsoError> {
    let message: Option<String> = if !(MIN_YEAR..=MAX_YEAR).contains(&parsed.year) {
        Some(format!("year {} is out of range", parsed.year))
    } else if !(1..=12).contains(&parsed.month) {
        Some("month must be in 1..12".to_owned())
    } else if parsed.day < 1 || parsed.day > days_in_month(parsed.year, parsed.month) {
        Some("day is out of range for month".to_owned())
    } else if !(0..=23).contains(&parsed.hour) {
        Some("hour must be in 0..23".to_owned())
    } else if !(0..=59).contains(&parsed.minute) {
        Some("minute must be in 0..59".to_owned())
    } else if !(0..=59).contains(&parsed.second) {
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
    if week <= 0 || week >= 53 {
        let first_weekday: i64 = (ymd_to_ordinal(year, 1, 1) + 6) % 7;
        let long_year: bool = first_weekday == 3 || (first_weekday == 2 && is_leap(year));
        if week != 53 || !long_year {
            return Err(-5);
        }
    }
    if weekday <= 0 || weekday >= 8 {
        return Err(-6);
    }
    let first_day: i64 = ymd_to_ordinal(year, 1, 1);
    let first_weekday: i64 = (first_day + 6) % 7;
    let week1_monday: i64 = first_day - first_weekday + if first_weekday > 3 { 7 } else { 0 };
    Ok(ordinal_to_ymd(week1_monday + (week - 1) * 7 + weekday - 1))
}

fn is_leap(year: i64) -> bool {
    year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)
}

fn days_in_month(year: i64, month: i64) -> i64 {
    match month {
        2 if is_leap(year) => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    }
}

fn ymd_to_ordinal(year: i64, month: i64, day: i64) -> i64 {
    let before_year: i64 = year - 1;
    let days_before_year: i64 =
        before_year * 365 + before_year / 4 - before_year / 100 + before_year / 400;
    let index: usize = usize::try_from(month.clamp(1, 12)).unwrap_or(1);
    days_before_year + DAYS_BEFORE_MONTH[index] + i64::from(month > 2 && is_leap(year)) + day
}

/// `ord_to_ymd`.
fn ordinal_to_ymd(ordinal: i64) -> (i64, i64, i64) {
    let mut days: i64 = ordinal - 1;
    let four_centuries: i64 = days / 146_097;
    days %= 146_097;
    let centuries: i64 = days / 36_524;
    days %= 36_524;
    let four_years: i64 = days / 1_461;
    days %= 1_461;
    let years: i64 = days / 365;
    days %= 365;
    let year: i64 = four_centuries * 400 + 1 + centuries * 100 + four_years * 4 + years;
    if years == 4 || centuries == 4 {
        return (year - 1, 12, 31);
    }
    let leap: bool = years == 3 && (four_years != 24 || centuries == 3);
    let mut month: i64 = (days + 50) >> 5;
    let month_index: usize = usize::try_from(month).unwrap_or(1);
    let mut preceding: i64 = DAYS_BEFORE_MONTH[month_index] + i64::from(month > 2 && leap);
    if preceding > days {
        month -= 1;
        preceding -= days_in_month(year, month);
    }
    (year, month, days - preceding + 1)
}
