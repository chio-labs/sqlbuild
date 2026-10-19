//! Leave a capture incomplete after its final flush failed, as Python's capture cleanup does.

use std::io::{self, Write};
use std::time::SystemTime;

use sqlbuild_core::json::main::dumps::dumps;
use sqlbuild_core::json::models::{JsonDialect, JsonInteger, JsonValue, OrjsonOptions};

use crate::compute_logs::_helpers::timestamps::{epoch_microseconds, utc_timestamp};
use crate::compute_logs::constants::{
    CAPTURE_FAILURE_LOGGER, CAPTURE_FAILURE_MESSAGE, DIAGNOSTIC_PRODUCER, DIAGNOSTIC_SCHEMA_VERSION,
};
use crate::compute_logs::models::{CaptureEnd, OpenCapture};

fn text(value: &str) -> JsonValue {
    JsonValue::String(value.to_owned())
}

/// The debug record `log_compute_capture_failure` writes to the capture's diagnostics.
fn capture_failure_record(invocation_id: &str, occurred_at: SystemTime) -> String {
    let record: JsonValue = JsonValue::Object(vec![
        ("fields".to_owned(), JsonValue::Object(Vec::new())),
        ("invocation_id".to_owned(), text(invocation_id)),
        ("log_stream_id".to_owned(), JsonValue::Null),
        ("logger".to_owned(), text(CAPTURE_FAILURE_LOGGER)),
        ("message".to_owned(), text(CAPTURE_FAILURE_MESSAGE)),
        (
            "occurred_at".to_owned(),
            text(&utc_timestamp(epoch_microseconds(occurred_at))),
        ),
        ("operation_id".to_owned(), JsonValue::Null),
        ("producer".to_owned(), text(DIAGNOSTIC_PRODUCER)),
        (
            "producer_version".to_owned(),
            text(env!("CARGO_PKG_VERSION")),
        ),
        ("resource_attempt_id".to_owned(), JsonValue::Null),
        ("resource_id".to_owned(), JsonValue::Null),
        ("run_id".to_owned(), JsonValue::Null),
        (
            "schema_version".to_owned(),
            JsonValue::Integer(JsonInteger::from(DIAGNOSTIC_SCHEMA_VERSION)),
        ),
        ("severity".to_owned(), text("debug")),
        ("source".to_owned(), text("python_logging")),
        ("statement_id".to_owned(), JsonValue::Null),
    ]);
    let options: OrjsonOptions = OrjsonOptions {
        sort_keys: true,
        ..OrjsonOptions::default()
    };
    dumps(&record, &JsonDialect::Orjson(options)).unwrap_or_default() + "\n"
}

/// Append the streams the command wrote and the capture failure, without completing it.
pub fn abandon_capture(capture: OpenCapture, end: &CaptureEnd) -> io::Result<()> {
    let OpenCapture {
        invocation_id,
        mut streams,
        ..
    } = capture;
    let [stdout, stderr, diagnostics] = streams.as_mut_slice() else {
        return Err(io::Error::other("capture streams are not open"));
    };
    stdout.write_all(&end.stdout)?;
    stderr.write_all(&end.stderr)?;
    diagnostics.write_all(capture_failure_record(&invocation_id, SystemTime::now()).as_bytes())?;
    for stream in [stdout, stderr, diagnostics] {
        stream.flush()?;
    }
    Ok(())
}
