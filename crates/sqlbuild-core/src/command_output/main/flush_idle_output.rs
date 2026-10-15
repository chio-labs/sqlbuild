//! The delivery worker's idle step: wait for records or flush a buffered record that is due.

use crate::command_output::_helpers::buffering::{flush_buffer, start};
use crate::command_output::constants::{FLUSH_INTERVAL_SECONDS, NO_SECONDS_REMAINING};
use crate::command_output::models::{IdleStep, OutputBuffer, RecordPriority};

/// Wait while nothing is buffered or the buffer is younger than the flush interval.
pub fn flush_idle_output(buffer: OutputBuffer, now: f64) -> (OutputBuffer, IdleStep) {
    let Some(started_at) = buffer.buffer_started_at else {
        return (buffer, IdleStep::Wait(None));
    };
    let remaining = started_at + FLUSH_INTERVAL_SECONDS - now;
    if remaining > NO_SECONDS_REMAINING {
        return (buffer, IdleStep::Wait(Some(remaining)));
    }
    let outcome = flush_buffer(start(buffer), RecordPriority::Bulk);
    (outcome.buffer, IdleStep::Flushed(outcome.drafts))
}
