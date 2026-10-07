//! YAML 1.1 timestamps: PyYAML's implicit resolver pattern and `construct_yaml_timestamp`.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::{ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};
use crate::yaml::_helpers::patterns::PatternCursor;
use crate::yaml::constants::{
    MICROSECOND_DIGITS, NEGATIVE_SIGN, SECONDS_PER_DAY, SECONDS_PER_MINUTE,
};

/// The `tz_sign`, `tz_hour` and `tz_minute` groups; `Z` has an empty sign.
type ZoneParts<'text> = (&'text str, &'text str, Option<&'text str>);

/// The groups of PyYAML's `timestamp_regexp`.
#[derive(Default)]
struct TimestampParts<'text> {
    year: &'text str,
    month: &'text str,
    day: &'text str,
    time: Option<(&'text str, &'text str, &'text str)>,
    fraction: Option<&'text str>,
    zone: Option<ZoneParts<'text>>,
}

fn is_digit(byte: u8) -> bool {
    byte.is_ascii_digit()
}

fn is_blank(byte: u8) -> bool {
    byte == b' ' || byte == b'\t'
}

/// Matches PyYAML's timestamp pattern over one text.
struct TimestampScanner<'text> {
    text: &'text str,
    cursor: PatternCursor<'text>,
}

impl<'text> TimestampScanner<'text> {
    /// Between `bounds.0` and `bounds.1` digits.
    fn digits(&mut self, bounds: (usize, usize)) -> Option<&'text str> {
        let start = self.cursor.position();
        let taken = self.cursor.up_to(bounds.1, is_digit);
        (taken >= bounds.0).then(|| &self.text[start..start + taken])
    }

    /// `-` followed by between `bounds.0` and `bounds.1` digits.
    fn dashed(&mut self, bounds: (usize, usize)) -> Option<&'text str> {
        self.cursor.literal("-").then(|| self.digits(bounds))?
    }

    /// `:` followed by two digits.
    fn sexagesimal(&mut self) -> Option<&'text str> {
        self.cursor.literal(":").then(|| self.digits((2, 2)))?
    }

    fn time(&mut self) -> Option<(&'text str, &'text str, &'text str)> {
        let separated = self.cursor.one(|byte| byte == b'T' || byte == b't')
            || self.cursor.up_to(usize::MAX, is_blank) > 0;
        if !separated {
            return None;
        }
        Some((
            self.digits((1, 2))?,
            self.sexagesimal()?,
            self.sexagesimal()?,
        ))
    }

    fn zone(&mut self) -> Option<ZoneParts<'text>> {
        let start = self.cursor.position();
        self.cursor.many(is_blank);
        if self.cursor.literal("Z") {
            return Some(("", "", None));
        }
        let sign_start = self.cursor.position();
        let zone = if self.cursor.one(|byte| byte == b'-' || byte == b'+') {
            self.digits((1, 2)).map(|hour| {
                (
                    &self.text[sign_start..=sign_start],
                    hour,
                    self.sexagesimal(),
                )
            })
        } else {
            None
        };
        if zone.is_none() {
            self.cursor.rewind(start);
        }
        zone
    }

    /// Match the constructor pattern; `strict_date` requires the resolver's two-digit date.
    fn parse(mut self, strict_date: bool) -> Option<TimestampParts<'text>> {
        let date_digits = if strict_date { (2, 2) } else { (1, 2) };
        let mut parts = TimestampParts {
            year: self.digits((4, 4))?,
            month: self.dashed(date_digits)?,
            day: self.dashed(date_digits)?,
            ..TimestampParts::default()
        };
        let time_start = self.cursor.position();
        parts.time = self.time();
        if parts.time.is_none() {
            self.cursor.rewind(time_start);
            return self.cursor.at_end().then_some(parts);
        }
        if self.cursor.literal(".") {
            let start = self.cursor.position();
            self.cursor.many(is_digit);
            parts.fraction = Some(&self.text[start..self.cursor.position()]);
        }
        parts.zone = self.zone();
        self.cursor.at_end().then_some(parts)
    }
}

fn parse_parts(text: &str, strict_date: bool) -> Option<TimestampParts<'_>> {
    TimestampScanner {
        text,
        cursor: PatternCursor::new(text),
    }
    .parse(strict_date)
}

/// Whether PyYAML's implicit timestamp resolver matches a plain scalar.
pub(crate) fn matches_implicit_timestamp(text: &str) -> bool {
    match parse_parts(text, false) {
        Some(parts) if parts.time.is_none() => parse_parts(text, true).is_some(),
        Some(_) => true,
        None => false,
    }
}

fn number(text: &str) -> i64 {
    text.bytes()
        .fold(0, |total, digit| total * 10 + i64::from(digit - b'0'))
}

fn invalid(message: &str) -> ConfigError {
    ConfigError::new(ConfigErrorKind::Construct, message)
}

fn microseconds(fraction: Option<&str>) -> i64 {
    let fraction = fraction.unwrap_or_default();
    let truncated = &fraction[..fraction.len().min(MICROSECOND_DIGITS)];
    number(&format!("{truncated:0<MICROSECOND_DIGITS$}"))
}

fn utc_offset(zone: Option<ZoneParts<'_>>) -> Result<Option<i32>, ConfigError> {
    let Some((sign, hour, minute)) = zone else {
        return Ok(None);
    };
    let minutes = number(hour) * 60 + minute.map_or(0, number);
    let seconds =
        i32::try_from(minutes).map_err(|_| invalid("offset is out of range"))? * SECONDS_PER_MINUTE;
    if seconds >= SECONDS_PER_DAY {
        return Err(invalid("offset must be strictly between -24 and 24 hours"));
    }
    Ok(Some(if sign == NEGATIVE_SIGN {
        -seconds
    } else {
        seconds
    }))
}

/// PyYAML's `construct_yaml_timestamp`: a date, or a naive or aware datetime.
pub(crate) fn construct_timestamp(text: &str) -> Result<ConfigValue, ConfigError> {
    let parts = parse_parts(text, false).ok_or_else(|| invalid("not a timestamp"))?;
    let date = ConfigDate::checked(number(parts.year), number(parts.month), number(parts.day))
        .ok_or_else(|| invalid("the date does not exist"))?;
    let Some((hour, minute, second)) = parts.time else {
        return Ok(ConfigValue::Date(date));
    };
    let time = ConfigTime::checked(
        number(hour),
        number(minute),
        number(second),
        microseconds(parts.fraction),
    )
    .ok_or_else(|| invalid("the time does not exist"))?;
    Ok(ConfigValue::DateTime(ConfigDateTime {
        date,
        time,
        utc_offset_seconds: utc_offset(parts.zone)?,
    }))
}
