//! `diagnostic_input_from_json`: a diagnostic from `diagnostic_log_to_json` text.

use serde_json::{Map, Value};

use crate::records::errors::RecordError;
use crate::records::models::{Correlations, DiagnosticInput};

fn text(object: &Map<String, Value>, field: &str) -> Result<String, RecordError> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(str::to_owned)
        .ok_or_else(|| RecordError::new(format!("diagnostic {field} must be a string")))
}

fn optional(object: &Map<String, Value>, field: &str) -> Option<String> {
    object.get(field).and_then(Value::as_str).map(str::to_owned)
}

/// The diagnostic encoded in `json`, numbered `sequence` within its invocation.
pub fn diagnostic_input_from_json(
    json: &str,
    sequence: u64,
) -> Result<DiagnosticInput, RecordError> {
    let parsed: Value = serde_json::from_str(json)
        .map_err(|error| RecordError::new(format!("diagnostic is not JSON: {error}")))?;
    let Value::Object(object) = parsed else {
        return Err(RecordError::new("diagnostic must be a JSON object"));
    };
    let fields: String = object
        .get("fields")
        .filter(|value| value.is_object())
        .map_or_else(|| "{}".to_owned(), Value::to_string);
    Ok(DiagnosticInput {
        sequence,
        occurred_at: text(&object, "occurred_at")?,
        severity: text(&object, "severity")?,
        logger: text(&object, "logger")?,
        source: text(&object, "source")?,
        message: text(&object, "message")?,
        fields,
        log_stream_id: optional(&object, "log_stream_id"),
        correlations: Correlations {
            run_id: optional(&object, "run_id"),
            resource_id: optional(&object, "resource_id"),
            resource_attempt_id: optional(&object, "resource_attempt_id"),
            operation_id: optional(&object, "operation_id"),
            statement_id: optional(&object, "statement_id"),
        },
    })
}
