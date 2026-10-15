//! `metadata.json` encoding, decoding and the storage's metadata validation.

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, StdlibJsonOptions};

use crate::compute_logs::_helpers::paths::validate_capture_id;
use crate::compute_logs::_helpers::timestamps::{parse_iso_instant, utc_date};
use crate::compute_logs::constants::COMPUTE_LOG_FORMAT_VERSION;
use crate::compute_logs::errors::{ComputeLogError, ComputeLogErrorKind};
use crate::compute_logs::models::{CaptureCompletion, CaptureDocument, CaptureInstant};

type Object = serde_json::Map<String, serde_json::Value>;

fn metadata_error(message: impl Into<String>) -> ComputeLogError {
    ComputeLogError::rejected(ComputeLogErrorKind::Metadata, message)
}

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

fn integer(value: i64) -> JsonValue {
    JsonValue::Integer(JsonInteger::from(value))
}

fn optional_text(value: Option<&str>) -> JsonValue {
    value.map_or(JsonValue::Null, text)
}

/// `metadata_to_json`: sorted keys, compact separators, non-ASCII kept, one trailing newline.
pub(crate) fn encode_document(document: &CaptureDocument) -> String {
    let mut fields: Vec<(String, JsonValue)> = vec![
        (
            "format_version".to_owned(),
            integer(document.format_version),
        ),
        ("invocation_id".to_owned(), text(&document.invocation_id)),
        ("command".to_owned(), text(&document.command)),
        ("project_dir".to_owned(), text(&document.project_dir)),
        ("started_at".to_owned(), text(&document.started_at.text)),
        ("capture_date".to_owned(), text(&document.capture_date)),
        (
            "target".to_owned(),
            optional_text(document.target.as_deref()),
        ),
        (
            "run_id".to_owned(),
            optional_text(document.run_id.as_deref()),
        ),
    ];
    if let Some(completion) = &document.completion {
        fields.extend([
            (
                "completed_at".to_owned(),
                text(&completion.completed_at.text),
            ),
            ("exit_code".to_owned(), integer(completion.exit_code)),
            ("stdout_bytes".to_owned(), integer(completion.stdout_bytes)),
            ("stderr_bytes".to_owned(), integer(completion.stderr_bytes)),
            (
                "diagnostics_bytes".to_owned(),
                integer(completion.diagnostics_bytes),
            ),
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

fn required<'a>(object: &'a Object, key: &str) -> Result<&'a serde_json::Value, ComputeLogError> {
    object
        .get(key)
        .ok_or_else(|| metadata_error(format!("invalid capture metadata: '{key}'")))
}

fn required_text(object: &Object, key: &str) -> Result<String, ComputeLogError> {
    required(object, key)?
        .as_str()
        .map(str::to_owned)
        .ok_or_else(|| metadata_error(format!("invalid capture metadata: {key} must be a string")))
}

fn optional_field(object: &Object, key: &str) -> Result<Option<String>, ComputeLogError> {
    match object.get(key) {
        None | Some(serde_json::Value::Null) => Ok(None),
        Some(serde_json::Value::String(value)) => Ok(Some(value.clone())),
        Some(_) => Err(metadata_error(format!(
            "invalid capture metadata: {key} must be a string or null"
        ))),
    }
}

fn instant(object: &Object, key: &str) -> Result<CaptureInstant, ComputeLogError> {
    let stored = required_text(object, key)?;
    let (micros, aware) = parse_iso_instant(&stored.replace('Z', "+00:00")).ok_or_else(|| {
        metadata_error(format!(
            "invalid capture metadata: Invalid isoformat string: '{stored}'"
        ))
    })?;
    Ok(CaptureInstant {
        micros,
        aware,
        text: stored,
    })
}

fn count(object: &Object, key: &str) -> Result<i64, ComputeLogError> {
    let value = required(object, key)?;
    if value.is_boolean() {
        return Err(metadata_error("exit_code and byte counts must be integers"));
    }
    value
        .as_i64()
        .ok_or_else(|| metadata_error("exit_code and byte counts must be integers"))
}

/// `metadata_from_json`: an initial or final capture document, or the metadata error raised.
pub(crate) fn decode_document(raw_json: &str) -> Result<CaptureDocument, ComputeLogError> {
    let parsed: serde_json::Value = serde_json::from_str(raw_json)
        .map_err(|error| metadata_error(format!("invalid capture metadata: {error}")))?;
    let serde_json::Value::Object(object) = parsed else {
        return Err(metadata_error("capture metadata must be a JSON object"));
    };
    let format_version = required(&object, "format_version")?;
    let invocation_id = required_text(&object, "invocation_id")?;
    let command = required_text(&object, "command")?;
    let project_dir = required_text(&object, "project_dir")?;
    let started_at = instant(&object, "started_at")?;
    let capture_date = required_text(&object, "capture_date")?;
    let target = optional_field(&object, "target")?;
    let run_id = optional_field(&object, "run_id")?;
    if format_version.is_boolean() || format_version.as_i64() != Some(COMPUTE_LOG_FORMAT_VERSION) {
        return Err(metadata_error("unsupported compute log format version"));
    }
    let completion = if object.contains_key("completed_at") {
        Some(CaptureCompletion {
            completed_at: instant(&object, "completed_at")?,
            exit_code: count(&object, "exit_code")?,
            stdout_bytes: count(&object, "stdout_bytes")?,
            stderr_bytes: count(&object, "stderr_bytes")?,
            diagnostics_bytes: count(&object, "diagnostics_bytes")?,
        })
    } else {
        None
    };
    Ok(CaptureDocument {
        format_version: COMPUTE_LOG_FORMAT_VERSION,
        invocation_id,
        command,
        project_dir,
        started_at,
        capture_date,
        target,
        run_id,
        completion,
    })
}

/// `_validate_metadata`: identity, format version, required text, timezones and byte counts.
pub(crate) fn validate_document(document: &CaptureDocument) -> Result<(), ComputeLogError> {
    validate_capture_id(&document.invocation_id)?;
    if document.format_version != COMPUTE_LOG_FORMAT_VERSION {
        return Err(metadata_error("unsupported compute log format version"));
    }
    if document.command.trim().is_empty() || document.project_dir.trim().is_empty() {
        return Err(metadata_error("command and project_dir must be non-empty"));
    }
    if !document.started_at.aware {
        return Err(metadata_error("started_at must be timezone-aware"));
    }
    if document.capture_date != utc_date(document.started_at.micros) {
        return Err(metadata_error(
            "capture_date must derive from UTC started_at",
        ));
    }
    if let Some(completion) = &document.completion {
        if !completion.completed_at.aware
            || completion.completed_at.micros < document.started_at.micros
        {
            return Err(metadata_error(
                "completed_at must be aware and not precede started_at",
            ));
        }
        if completion
            .stdout_bytes
            .min(completion.stderr_bytes)
            .min(completion.diagnostics_bytes)
            < 0
        {
            return Err(metadata_error("final byte counts must be nonnegative"));
        }
    }
    Ok(())
}
