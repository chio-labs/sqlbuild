//! `metadata_to_json` of a capture the native `sqb` replay records.

use crate::compute_logs::_helpers::document::encode_document;
use crate::compute_logs::_helpers::timestamps::{epoch_microseconds, utc_date, utc_timestamp};
use crate::compute_logs::constants::COMPUTE_LOG_FORMAT_VERSION;
use crate::compute_logs::models::{
    CaptureCompletion, CaptureDocument, CaptureEnd, CaptureInstant, CaptureStart,
};

/// The streams' final byte counts: stdout, stderr and diagnostics.
pub(crate) type ByteCounts = (usize, usize, usize);

fn utc_instant(micros: i64) -> CaptureInstant {
    CaptureInstant {
        micros,
        aware: true,
        text: utc_timestamp(micros),
    }
}

fn count(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

/// `metadata_to_json`: sorted keys, compact separators, non-ASCII kept, one trailing newline.
pub(crate) fn metadata_json(
    (start, invocation_id): (&CaptureStart, &str),
    end: Option<(&CaptureEnd, i64, ByteCounts)>,
) -> String {
    let started_at = epoch_microseconds(start.started_at);
    encode_document(&CaptureDocument {
        format_version: COMPUTE_LOG_FORMAT_VERSION,
        invocation_id: invocation_id.to_owned(),
        command: start.command.clone(),
        project_dir: start.project_dir.clone(),
        started_at: utc_instant(started_at),
        capture_date: utc_date(started_at),
        target: start.target.clone(),
        run_id: None,
        completion: end.map(
            |(end, completed_at, (stdout_bytes, stderr_bytes, diagnostics_bytes))| {
                CaptureCompletion {
                    completed_at: utc_instant(completed_at),
                    exit_code: end.exit_code,
                    stdout_bytes: count(stdout_bytes),
                    stderr_bytes: count(stderr_bytes),
                    diagnostics_bytes: count(diagnostics_bytes),
                }
            },
        ),
    })
}
