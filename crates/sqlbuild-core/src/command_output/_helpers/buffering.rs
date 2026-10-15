//! `OutputCaptureDispatcher` fragment buffering: chunk, coalesce and flush into record drafts.

use crate::command_output::_helpers::text::{chunk_text, strict_utf8_length, strip_ansi};
use crate::command_output::errors::UnencodableText;
use crate::command_output::models::{
    BufferOutcome, OutputBuffer, OutputStream, RecordDraft, RecordPriority,
};
use crate::command_output::types::PassText;

/// `_enqueue_chunks`: one draft per chunk with consecutive sequence numbers.
fn enqueue_chunks(
    mut outcome: BufferOutcome,
    (stream, chunks): (OutputStream, Vec<PassText>),
    priority: RecordPriority,
) -> BufferOutcome {
    let chunk_count = chunks.len();
    for (chunk_index, message) in chunks.into_iter().enumerate() {
        let sequence = outcome.buffer.sequence;
        outcome.buffer.sequence += 1;
        outcome.drafts.push(RecordDraft {
            sequence,
            stream,
            message,
            chunk_index,
            chunk_count,
            priority,
            dropped_records: 0,
        });
    }
    outcome
}

/// `_flush_buffer`: turn the coalesced buffer into one record.
pub(crate) fn flush_buffer(mut outcome: BufferOutcome, priority: RecordPriority) -> BufferOutcome {
    let Some(stream) = outcome.buffer.buffer_stream else {
        return outcome;
    };
    if outcome.buffer.buffer_part_count == 0 {
        return outcome;
    }
    let text = std::mem::take(&mut outcome.buffer.buffer_text);
    outcome.buffer.buffer_stream = None;
    outcome.buffer.buffer_part_count = 0;
    outcome.buffer.buffer_bytes = 0;
    outcome.buffer.buffer_started_at = None;
    enqueue_chunks(outcome, (stream, vec![text]), priority)
}

fn failed(mut outcome: BufferOutcome, error: UnencodableText) -> BufferOutcome {
    outcome.error = Some(error);
    outcome
}

/// `_buffer_text_fragment`: chunk and coalesce one ANSI-free fragment; failures end the outcome.
pub(crate) fn buffer_fragment(
    mut outcome: BufferOutcome,
    (stream, text): (OutputStream, &[u8]),
    (immediate, now): (RecordPriority, f64),
) -> BufferOutcome {
    let mut chunks = match chunk_text(&strip_ansi(text), outcome.buffer.max_record_bytes) {
        Ok(chunks) => chunks,
        Err(error) => return failed(outcome, error),
    };
    if chunks.len() > 1 {
        outcome = flush_buffer(outcome, RecordPriority::Bulk);
        return enqueue_chunks(outcome, (stream, chunks), immediate);
    }
    let chunk = chunks.pop().unwrap_or_default();
    if outcome
        .buffer
        .buffer_stream
        .is_some_and(|buffered| buffered != stream)
    {
        outcome = flush_buffer(outcome, RecordPriority::Bulk);
    }
    let chunk_bytes = match strict_utf8_length(&chunk) {
        Ok(length) => length,
        Err(error) => return failed(outcome, error),
    };
    let exceeds = i64::try_from(outcome.buffer.buffer_bytes + chunk_bytes).unwrap_or(i64::MAX)
        > outcome.buffer.max_record_bytes;
    if outcome.buffer.buffer_part_count > 0 && exceeds {
        outcome = flush_buffer(outcome, RecordPriority::Bulk);
    }
    if outcome.buffer.buffer_part_count == 0 {
        outcome.buffer.buffer_stream = Some(stream);
        outcome.buffer.buffer_started_at = Some(now);
    }
    outcome.buffer.buffer_text.extend_from_slice(&chunk);
    outcome.buffer.buffer_part_count += 1;
    outcome.buffer.buffer_bytes += chunk_bytes;
    outcome
}

/// A fresh outcome continuing from `buffer`.
pub(crate) fn start(buffer: OutputBuffer) -> BufferOutcome {
    BufferOutcome {
        buffer,
        drafts: Vec::new(),
        error: None,
    }
}

/// The index of `stream` in per-stream arrays: stdout, then stderr.
pub(crate) fn stream_slot(stream: OutputStream) -> usize {
    match stream {
        OutputStream::Stdout => 0,
        OutputStream::Stderr => 1,
    }
}
