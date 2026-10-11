//! `metadata_to_json` and the subset of `metadata_from_json` validation pruning relies on.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::compute_logs::_helpers::timestamps::{
    epoch_microseconds, parse_utc_timestamp, utc_date, utc_timestamp,
};
use crate::compute_logs::constants::COMPUTE_LOG_FORMAT_VERSION;
use crate::compute_logs::models::{CaptureEnd, CaptureStart};

/// The streams' final byte counts: stdout, stderr and diagnostics.
pub(crate) type ByteCounts = (usize, usize, usize);

/// A stored capture's identity and the instant pruning orders it by.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct StoredCapture {
    pub(crate) invocation_id: String,
    pub(crate) capture_date: String,
    /// `completed_at`, or `started_at` while incomplete, in microseconds.
    pub(crate) order_instant: i64,
}

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

fn count(value: usize) -> JsonValue {
    integer(i64::try_from(value).unwrap_or(i64::MAX))
}

/// `metadata_to_json`: sorted keys, compact separators, non-ASCII kept, one trailing newline.
pub(crate) fn metadata_json(
    (start, invocation_id): (&CaptureStart, &str),
    end: Option<(&CaptureEnd, i64, ByteCounts)>,
) -> String {
    let started_at = epoch_microseconds(start.started_at);
    let mut fields: Vec<(String, JsonValue)> = vec![
        (
            "format_version".to_owned(),
            integer(COMPUTE_LOG_FORMAT_VERSION),
        ),
        ("invocation_id".to_owned(), text(invocation_id)),
        ("command".to_owned(), text(&start.command)),
        ("project_dir".to_owned(), text(&start.project_dir)),
        ("started_at".to_owned(), text(&utc_timestamp(started_at))),
        ("capture_date".to_owned(), text(&utc_date(started_at))),
        (
            "target".to_owned(),
            start.target.as_deref().map_or(JsonValue::Null, text),
        ),
        ("run_id".to_owned(), JsonValue::Null),
    ];
    if let Some((end, completed_at, (stdout_bytes, stderr_bytes, diagnostics_bytes))) = end {
        fields.extend([
            (
                "completed_at".to_owned(),
                text(&utc_timestamp(completed_at)),
            ),
            ("exit_code".to_owned(), integer(end.exit_code)),
            ("stdout_bytes".to_owned(), count(stdout_bytes)),
            ("stderr_bytes".to_owned(), count(stderr_bytes)),
            ("diagnostics_bytes".to_owned(), count(diagnostics_bytes)),
        ]);
    }
    let options = StdlibJsonOptions {
        ensure_ascii: false,
        sort_keys: true,
        ..StdlibJsonOptions::new(None).with_separators(",", ":")
    };
    let encoded =
        dumps(&JsonValue::Object(fields), &JsonDialect::Stdlib(options)).unwrap_or_default();
    format!("{encoded}\n")
}

fn string_field<'a>(
    object: &'a serde_json::Map<String, serde_json::Value>,
    key: &str,
) -> Option<&'a str> {
    object.get(key).and_then(serde_json::Value::as_str)
}

/// The capture a stored `metadata.json` describes, or `None` where Python's validation rejects it.
pub(crate) fn stored_capture(json: &str) -> Option<StoredCapture> {
    let Ok(serde_json::Value::Object(object)) = serde_json::from_str::<serde_json::Value>(json)
    else {
        return None;
    };
    if object
        .get("format_version")
        .and_then(serde_json::Value::as_i64)
        != Some(COMPUTE_LOG_FORMAT_VERSION)
    {
        return None;
    }
    let invocation_id = string_field(&object, "invocation_id")?;
    let capture_date = string_field(&object, "capture_date")?;
    let command = string_field(&object, "command")?;
    let project_dir = string_field(&object, "project_dir")?;
    let started_at = parse_utc_timestamp(string_field(&object, "started_at")?)?;
    if command.trim().is_empty()
        || project_dir.trim().is_empty()
        || utc_date(started_at) != capture_date
    {
        return None;
    }
    let order_instant = match object.get("completed_at") {
        None => started_at,
        Some(value) => {
            let completed_at = parse_utc_timestamp(value.as_str()?)?;
            let integers = [
                "exit_code",
                "stdout_bytes",
                "stderr_bytes",
                "diagnostics_bytes",
            ];
            if completed_at < started_at
                || !integers
                    .iter()
                    .all(|key| object.get(*key).is_some_and(serde_json::Value::is_i64))
            {
                return None;
            }
            completed_at
        }
    };
    Some(StoredCapture {
        invocation_id: invocation_id.to_owned(),
        capture_date: capture_date.to_owned(),
        order_instant,
    })
}
