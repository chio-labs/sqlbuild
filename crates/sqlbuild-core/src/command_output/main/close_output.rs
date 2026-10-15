//! `OutputCaptureDispatcher.close`: flush unterminated tails and the buffer as terminal records.

use crate::command_output::_helpers::buffering::{buffer_fragment, flush_buffer, start};
use crate::command_output::models::{BufferOutcome, OutputBuffer, OutputStream, RecordPriority};

/// Flush each stream's partial line and the coalesced buffer with terminal priority.
pub fn close_output(buffer: OutputBuffer, now: f64) -> BufferOutcome {
    let partials = buffer.partials.clone();
    let mut outcome = start(buffer);
    for (stream, partial) in [OutputStream::Stdout, OutputStream::Stderr]
        .into_iter()
        .zip(partials)
    {
        if partial.is_empty() {
            continue;
        }
        outcome = buffer_fragment(outcome, (stream, &partial), (RecordPriority::Terminal, now));
        if outcome.error.is_some() {
            return outcome;
        }
        outcome = flush_buffer(outcome, RecordPriority::Terminal);
    }
    outcome = flush_buffer(outcome, RecordPriority::Terminal);
    outcome.buffer.partials = [Vec::new(), Vec::new()];
    outcome
}
