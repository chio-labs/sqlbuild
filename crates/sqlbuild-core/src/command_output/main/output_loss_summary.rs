//! `_enqueue_loss_summary`: the terminal stderr record reporting dropped output.

use crate::command_output::models::{
    OutputBuffer, OutputQueue, OutputStream, RecordDraft, RecordPriority,
};

/// The loss record counting drops so far, including the bulk record it is about to displace.
pub fn output_loss_summary<T>(
    mut buffer: OutputBuffer,
    queue: &OutputQueue<T>,
) -> (OutputBuffer, RecordDraft) {
    let displaces_bulk = queue.items.len() >= queue.capacity
        && queue
            .items
            .iter()
            .any(|(_, priority)| *priority == RecordPriority::Bulk);
    let dropped = queue.dropped + u64::from(displaces_bulk);
    let sequence = buffer.sequence;
    buffer.sequence += 1;
    let draft = RecordDraft {
        sequence,
        stream: OutputStream::Stderr,
        message: format!("SQLBuild output export dropped {dropped} record(s)").into_bytes(),
        chunk_index: 0,
        chunk_count: 1,
        priority: RecordPriority::Terminal,
        dropped_records: dropped,
    };
    (buffer, draft)
}
