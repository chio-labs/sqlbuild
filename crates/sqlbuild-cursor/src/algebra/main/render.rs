//! `render`: a cursor value in the cursor output format.

use crate::algebra::constants::{MICROS_PER_SECOND, SECONDS_PER_HOUR, SECONDS_PER_MINUTE};
use crate::algebra::errors::CursorError;
use crate::algebra::models::{CivilDate, Scalar, ScalarValue, ZoneOffset};
use crate::algebra::types::ZoneRules;

fn date_text(date: &CivilDate) -> String {
    format!("{:04}-{:02}-{:02}", date.year, date.month, date.day)
}

/// `timedelta` offset text as `datetime.isoformat` appends it.
fn offset_text(offset: i64) -> String {
    let sign: char = if offset < 0 { '-' } else { '+' };
    let magnitude: i128 = i128::from(offset).abs();
    let seconds: i128 = magnitude / MICROS_PER_SECOND;
    let microseconds: i128 = magnitude % MICROS_PER_SECOND;
    let mut text: String = format!(
        "{sign}{:02}:{:02}",
        seconds / SECONDS_PER_HOUR,
        seconds % SECONDS_PER_HOUR / SECONDS_PER_MINUTE
    );
    if seconds % SECONDS_PER_MINUTE != 0 || microseconds != 0 {
        text.push_str(&format!(":{:02}", seconds % SECONDS_PER_MINUTE));
    }
    if microseconds != 0 {
        text.push_str(&format!(".{microseconds:06}"));
    }
    text
}

/// The integer's digits, the parsed timestamp text, or the value's `isoformat()`.
pub fn render(value: &Scalar, rules: &dyn ZoneRules) -> Result<String, CursorError> {
    let timestamp = match &value.value {
        ScalarValue::Integer(number) => return Ok(number.to_string()),
        ScalarValue::Date(date) => return Ok(date_text(date)),
        ScalarValue::Timestamp(timestamp) => timestamp,
    };
    if let Some(text) = &timestamp.source_text {
        return Ok(text.clone());
    }
    let local = &timestamp.local;
    let mut text: String = format!(
        "{}T{:02}:{:02}:{:02}",
        date_text(&local.date),
        local.hour,
        local.minute,
        local.second
    );
    if local.microsecond != 0 {
        text.push_str(&format!(".{:06}", local.microsecond));
    }
    let offset: Option<i64> = match timestamp.offset {
        ZoneOffset::Naive => None,
        ZoneOffset::Fixed(offset) => Some(offset),
        ZoneOffset::External(template) => rules.utc_offset(template, local, timestamp.fold)?,
    };
    if let Some(offset) = offset {
        text.push_str(&offset_text(offset));
    }
    Ok(text)
}
