//! `_put`: accept one record into the bounded queue, displacing bulk output for terminal records.

use crate::command_output::models::{OutputQueue, RecordPriority};

/// Queue `item`, or drop it (or the oldest bulk record for a terminal one) when full.
pub fn queue_output_record<T>(
    mut queue: OutputQueue<T>,
    item: T,
    priority: RecordPriority,
) -> OutputQueue<T> {
    queue.accepted += 1;
    if queue.items.len() < queue.capacity {
        queue.items.push_back((item, priority));
        return queue;
    }
    if priority == RecordPriority::Terminal
        && let Some(position) = queue
            .items
            .iter()
            .position(|(_, queued)| *queued == RecordPriority::Bulk)
    {
        queue.items.remove(position);
        queue.dropped += 1;
        queue.items.push_back((item, priority));
        return queue;
    }
    queue.dropped += 1;
    queue
}
