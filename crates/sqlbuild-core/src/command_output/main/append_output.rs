//! `OutputCaptureDispatcher.append`: split a stream fragment into complete lines and buffer them.

use crate::command_output::_helpers::buffering::{buffer_fragment, start, stream_slot};
use crate::command_output::_helpers::text::split_lines;
use crate::command_output::models::{BufferOutcome, OutputBuffer, OutputStream, RecordPriority};

/// Buffer the complete lines of `text`, keeping an unterminated tail per stream.
pub fn append_output(
    mut buffer: OutputBuffer,
    (stream, text): (OutputStream, &[u8]),
    now: f64,
) -> BufferOutcome {
    let slot = stream_slot(stream);
    let mut combined = std::mem::take(&mut buffer.partials[slot]);
    combined.extend_from_slice(text);
    let mut lines = split_lines(&combined);
    let complete = lines
        .last()
        .is_some_and(|line| line.ends_with(b"\n") || line.ends_with(b"\r"));
    let trailing: Vec<u8> = match complete {
        true => Vec::new(),
        false => lines.pop().map(<[u8]>::to_vec).unwrap_or_default(),
    };
    buffer.partials[slot] = trailing;
    let mut outcome = start(buffer);
    for line in lines {
        outcome = buffer_fragment(outcome, (stream, line), (RecordPriority::Bulk, now));
        if outcome.error.is_some() {
            break;
        }
    }
    outcome
}
