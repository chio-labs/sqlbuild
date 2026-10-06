//! Convert a parsed TOML document into the values `tomllib` returns.

use crate::errors::{ConfigError, ConfigErrorKind};
use crate::models::{ConfigDate, ConfigDateTime, ConfigTime, ConfigValue};
use toml_edit::{Array, Datetime, Document, InlineTable, Item, Key, Offset, Table, Value};

const NANOSECONDS_PER_MICROSECOND: u32 = 1_000;
/// No key inside: such values sort by their own key alone.
const NO_POSITION: usize = usize::MAX;
/// The deepest value nesting converted natively; the version check keeps documents well within it.
const MAX_DEPTH: usize = 512;
const SECONDS_PER_MINUTE: i32 = 60;

fn invalid_datetime(message: &str) -> ConfigError {
    ConfigError::new(
        ConfigErrorKind::Syntax,
        format!("invalid date or datetime: {message}"),
    )
}

fn date(value: toml_edit::Date) -> Result<ConfigDate, ConfigError> {
    ConfigDate::checked(
        i64::from(value.year),
        i64::from(value.month),
        i64::from(value.day),
    )
    .ok_or_else(|| invalid_datetime("the date does not exist"))
}

fn time(value: toml_edit::Time) -> Result<ConfigTime, ConfigError> {
    let second = value
        .second
        .ok_or_else(|| invalid_datetime("seconds are required before TOML 1.1"))?;
    ConfigTime::checked(
        i64::from(value.hour),
        i64::from(value.minute),
        i64::from(second),
        i64::from(value.nanosecond.unwrap_or_default() / NANOSECONDS_PER_MICROSECOND),
    )
    .ok_or_else(|| invalid_datetime("the time does not exist"))
}

fn datetime(value: &Datetime) -> Result<ConfigValue, ConfigError> {
    let offset = value.offset.map(|offset| match offset {
        Offset::Z => 0,
        Offset::Custom { minutes } => i32::from(minutes) * SECONDS_PER_MINUTE,
    });
    match (value.date, value.time) {
        (Some(day), Some(clock)) => Ok(ConfigValue::DateTime(ConfigDateTime {
            date: date(day)?,
            time: time(clock)?,
            utc_offset_seconds: offset,
        })),
        (Some(day), None) => date(day).map(ConfigValue::Date),
        (None, Some(clock)) => time(clock).map(ConfigValue::Time),
        (None, None) => Err(invalid_datetime("empty datetime")),
    }
}

/// A converted value and the earliest source offset of a key inside it, which orders tables.
type Positioned = (ConfigValue, usize);

fn too_deep() -> ConfigError {
    ConfigError::new(
        ConfigErrorKind::Unsupported,
        "TOML values nest deeper than the native limit",
    )
}

fn key_position(key: Option<&Key>) -> usize {
    key.and_then(Key::span)
        .map_or(NO_POSITION, |span| span.start)
}

/// A dictionary in `tomllib`'s order: keys in the order their first statement created them.
fn ordered_map(mut entries: Vec<(usize, String, ConfigValue)>) -> Positioned {
    entries.sort_by_key(|(position, _, _)| *position);
    let first = entries
        .first()
        .map_or(NO_POSITION, |(position, _, _)| *position);
    let converted: Vec<(ConfigValue, ConfigValue)> = entries
        .into_iter()
        .map(|(_, key, value)| (ConfigValue::String(key), value))
        .collect();
    (ConfigValue::Map(converted), first)
}

fn list(items: Vec<Positioned>) -> Positioned {
    let first = items
        .iter()
        .map(|(_, position)| *position)
        .min()
        .unwrap_or(NO_POSITION);
    let values: Vec<ConfigValue> = items.into_iter().map(|(value, _)| value).collect();
    (ConfigValue::List(values), first)
}

fn array(values: &Array, depth: usize) -> Result<Positioned, ConfigError> {
    values
        .iter()
        .map(|item| value(item, depth + 1))
        .collect::<Result<Vec<_>, _>>()
        .map(list)
}

fn inline_table(entries: &InlineTable, depth: usize) -> Result<Positioned, ConfigError> {
    let mut converted: Vec<(usize, String, ConfigValue)> = Vec::new();
    for (key, item) in entries.iter() {
        let (converted_value, inner) = value(item, depth + 1)?;
        let position = key_position(entries.key(key)).min(inner);
        converted.push((position, key.to_owned(), converted_value));
    }
    Ok(ordered_map(converted))
}

fn value(item: &Value, depth: usize) -> Result<Positioned, ConfigError> {
    if depth > MAX_DEPTH {
        return Err(too_deep());
    }
    let scalar = |converted: ConfigValue| (converted, NO_POSITION);
    match item {
        Value::String(text) => Ok(scalar(ConfigValue::String(text.value().clone()))),
        Value::Integer(number) => Ok(scalar(ConfigValue::Integer(*number.value()))),
        Value::Float(number) => Ok(scalar(ConfigValue::Float(*number.value()))),
        Value::Boolean(flag) => Ok(scalar(ConfigValue::Bool(*flag.value()))),
        Value::Datetime(moment) => datetime(moment.value()).map(scalar),
        Value::Array(values) => array(values, depth),
        Value::InlineTable(entries) => inline_table(entries, depth),
    }
}

fn item(entry: &Item, depth: usize) -> Result<Option<Positioned>, ConfigError> {
    match entry {
        Item::None => Ok(None),
        Item::Value(scalar) => value(scalar, depth).map(Some),
        Item::Table(entries) => table(entries, depth).map(Some),
        Item::ArrayOfTables(tables) => tables
            .iter()
            .map(|entries| table(entries, depth + 1))
            .collect::<Result<Vec<_>, _>>()
            .map(|tables| Some(list(tables))),
    }
}

fn table(entries: &Table, depth: usize) -> Result<Positioned, ConfigError> {
    if depth > MAX_DEPTH {
        return Err(too_deep());
    }
    let mut converted: Vec<(usize, String, ConfigValue)> = Vec::new();
    for (key, entry) in entries.iter() {
        if let Some((converted_value, inner)) = item(entry, depth + 1)? {
            let position = key_position(entries.key(key)).min(inner);
            converted.push((position, key.to_owned(), converted_value));
        }
    }
    Ok(ordered_map(converted))
}

/// Parse `text` and convert its root table.
pub(crate) fn parse_document(text: &str) -> Result<ConfigValue, ConfigError> {
    let document = Document::parse(text).map_err(|error| {
        let offset = error.span().map_or(0, |span| span.start);
        ConfigError {
            kind: ConfigErrorKind::Syntax,
            message: error.message().to_owned(),
            line: Some(text.get(..offset).unwrap_or(text).matches('\n').count() + 1),
            column: None,
        }
    })?;
    table(document.as_table(), 0).map(|(converted, _)| converted)
}
